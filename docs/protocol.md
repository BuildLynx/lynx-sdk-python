# The Lynx Protocol

**Version: A-01.01**

---

## 1. Introduction

Lynx is a **Lightweight Network Extension of MQTT**. It defines a set of conventions on top of standard MQTT that give sensor networks self-describing services, structured data channels, automatic discovery, and schema-validated payloads -- all without replacing MQTT or requiring a custom broker.

Any standard MQTT v5 client can participate in a Lynx network. Lynx simply defines *how* topics are named, *what* payloads look like, and *which* topics carry special meaning. The result is a network where every service advertises what it is, what data it produces, and what commands it accepts -- and where observers can discover and monitor the entire topology automatically.

### Design Philosophy

- **Minimal complexity.** Lynx adds structure to MQTT, not a new transport. If you know MQTT, you already know most of Lynx.
- **Self-describing.** Every Lynx component publishes an "About" payload that fully describes its identity, capabilities, endpoints, and current status.
- **Schema-enforced.** Payloads are JSON validated against JSON Schema (Draft 7), so producers and consumers agree on shape at protocol level.
- **Composable.** Services contain Channels; Nodes contain Services. The hierarchy is simple and extensible.

---

## 2. Overview

Lynx organizes an MQTT broker into a layered hierarchy of **Nodes**, **Services**, and **Channels**.

```mermaid
graph TD
    Broker["MQTT Broker"]
    Node["Node"]
    ServiceA["Service A"]
    ServiceB["Service B"]
    ChannelA1["Channel A1"]
    ChannelA2["Channel A2"]
    ChannelB1["Channel B1"]

    Broker --- Node
    Node --- ServiceA
    Node --- ServiceB
    ServiceA --- ChannelA1
    ServiceA --- ChannelA2
    ServiceB --- ChannelB1
```

| Layer | Role |
|-------|------|
| **Node** | Broker-adjacent coordinator. Monitors connected Services and child Nodes, maintains a NetworkState tree. |
| **Service** | Application boundary. Owns an MQTT client, a time source, and one or more Channels. Publishes a retained self-description. |
| **Channel** | Single data stream. Accepts Poll/Stream/Stop commands and publishes timestamped sample arrays. |

A Lynx network can run with just a Service connected to a broker -- Nodes are optional. Any vanilla MQTT client can subscribe to Lynx topics and consume the JSON payloads directly.

---

## 3. Use Cases

### 3.1 Ideal Fits

- **Sensor networks and device telemetry.** A Raspberry Pi publishing CPU load, temperature, and memory stats. An embedded device reporting accelerometer readings. Lynx's Channel abstraction maps naturally to periodic or event-driven sensor data.
- **Edge monitoring and fleet dashboards.** Nodes at the edge track which Services are alive, their status, and their channel states -- forming a real-time topology view.
- **Schema-enforced IoT data pipelines.** Every Channel declares its output schema. Consumers know the shape of the data before the first sample arrives.
- **Self-describing, discoverable service networks.** No external service registry needed. Subscribe to `+/@/About` and the network describes itself.
- **Rapid prototyping.** Define a Service, attach a Channel with a generator function, call `start()`. Data flows in seconds.
- **Lightweight data acquisition (DAQ) systems.** Stream parameters (`interval`, `numSamples`, `paginate`) give fine-grained control over sampling without custom protocol work.

### 3.2 Non-Ideal Fits

- **No MQTT broker available.** Lynx is built on MQTT. Without a broker, the protocol has no transport.
- **Heavy computation inside sampling loops.** Channel sampling runs in a thread with a cooperative `continue_sampling()` check. CPU-bound or long-blocking work inside the generator can starve other channels or delay Stop commands.
- **Non-JSON / binary payloads.** Lynx payloads are JSON objects. Large binary data (images, video, raw ADC buffers) would need base64 encoding or an out-of-band mechanism.
- **Very large-scale deployments (100k+ devices).** Every Service publishes a retained `@/About` message. At extreme scale, the broker's retained message store and the wildcard subscription `+/@/About` may become bottlenecks.
- **RPC-heavy / request-response architectures.** Lynx is oriented around pub/sub data streams, not request-response patterns. While `?/About` is a query-response pattern, Channels are one-directional output streams.

---

## 4. Core Concepts

### 4.1 Component

The base entity in Lynx. Every Component has:

- **Identity**: `id`, `title`, `description`, `lynx_version`
- **Endpoints**: a set of MQTT topics it publishes to or subscribes on
- **Status**: a `state` (idle, busy, disconnected, disabled) and an optional `action` describing work in progress
- **About**: a method to produce a full self-description as a JSON object

### 4.2 Component Types

```mermaid
classDiagram
    Component <|-- ClientComponent
    ClientComponent <|-- Service
    ClientComponent <|-- Node
    Component <|-- Channel

    class Component {
        id: string
        title: string
        description: string
        lynx_version: string
        endpoints: dict
        status: dict
        produce_about() dict
    }

    class ClientComponent {
        mqtt_client: MqttClient
        time_source: TimeSource
        logger: Logger
        network_state: NetworkState
        start()
    }

    class Service {
        channels: dict
        publish_about()
    }

    class Node {
        about_cache: dict
        parent_node_socket: tuple
        publish_about()
    }

    class Channel {
        service: Service
        sample_function: Callable
        poll_handler()
        start_stream_handler()
        stop_handler()
    }
```

- **Service** and **Node** are *client components* -- they own an MQTT connection. A Channel does not; it accesses the broker through its parent Service.
- A Service contains zero or more Channels. A Node monitors zero or more Services and child Nodes.

### 4.3 Component States

| State | Meaning |
|-------|---------|
| `idle` | Ready to accept commands. |
| `busy` | Actively executing a command (e.g., streaming). |
| `disconnected` | Lost connection to the broker (set via LWT). |
| `disabled` | Intentionally taken offline. |

### 4.4 Endpoints

An Endpoint is a single MQTT topic with:
- A **direction**: `sub` (subscribes and handles incoming messages), `pub` (publishes outgoing messages), or `pubsub`.
- A **payload schema**: JSON Schema (Draft 7) describing the expected payload.
- A **description**: human-readable purpose.

### 4.5 About

Every component can produce an "About" payload -- a JSON object that fully describes the component. Services and Nodes publish their About as a **retained** MQTT message so that new subscribers immediately receive the current state of the network.

### 4.6 Contents

A filtering mechanism that lets consumers request only the parts of a payload they care about. The `contents` parameter appears on `?/About` queries and on channel Poll/Stream commands. It supports several modes:

| `contents` value | Behavior |
|------------------|----------|
| `true` (or `{}`) | Return the full payload. |
| `false` | Return only values that changed since the last sample (change-of-value). |
| `{"key1": true, "key2": false}` | Select specific keys; per-key `true`/`false` controls inclusion or change-of-value. |
| `"<xxh32 hex string>"` | Return the payload only if its xxh32 hash differs from the provided hash. |

---

## 5. Topic Structure

Lynx uses symbolic prefixes in topic segments to distinguish system topics from data topics. The general pattern is:

```
{serviceId}/{channelId?}/{prefix}/{action}
```

### 5.1 Symbolic Prefixes

| Prefix | Name | Meaning | Example |
|--------|------|---------|---------|
| `@` | System | Published by the component automatically (About, Notice) | `deviceWatcher/@/About` |
| `?` | Query | Subscribe to receive a query; response published on `@` | `deviceWatcher/?/About` |
| `!` | Command | Channel commands (Poll, Stream, Stop) | `deviceWatcher/cpuLoad/!/Stream` |
| `<` | Output | Channel data output | `deviceWatcher/cpuLoad/<` |

### 5.2 Topic Tree Example

For a service `deviceWatcher` with channels `cpuLoad` and `memory`:

```mermaid
graph LR
    subgraph service ["deviceWatcher"]
        SysAbout["@/About"]
        QueryAbout["?/About"]
        SysNotice["@/Notice"]
    end

    subgraph cpuLoad ["deviceWatcher/cpuLoad"]
        CpuPoll["!/Poll"]
        CpuStream["!/Stream"]
        CpuStop["!/Stop"]
        CpuOut["&lt;"]
    end

    subgraph memory ["deviceWatcher/memory"]
        MemPoll["!/Poll"]
        MemStream["!/Stream"]
        MemStop["!/Stop"]
        MemOut["&lt;"]
    end
```

The full topic strings for this service are:

| Topic | Direction | QoS | Retained | Purpose |
|-------|-----------|-----|----------|---------|
| `deviceWatcher/@/About` | pub | 1 | yes | Service self-description |
| `deviceWatcher/?/About` | sub | -- | -- | Query service info |
| `deviceWatcher/@/Notice` | pub | 1 | no | Log/alert messages |
| `deviceWatcher/cpuLoad/!/Poll` | sub | -- | -- | Request a single sample |
| `deviceWatcher/cpuLoad/!/Stream` | sub | -- | -- | Start continuous sampling |
| `deviceWatcher/cpuLoad/!/Stop` | sub | -- | -- | Stop active sampling |
| `deviceWatcher/cpuLoad/<` | pub | 0 | no | Sample data output |
| `deviceWatcher/memory/!/Poll` | sub | -- | -- | Request a single sample |
| `deviceWatcher/memory/!/Stream` | sub | -- | -- | Start continuous sampling |
| `deviceWatcher/memory/!/Stop` | sub | -- | -- | Stop active sampling |
| `deviceWatcher/memory/<` | pub | 0 | no | Sample data output |

### 5.3 Topic Construction Rules

- **Service endpoints**: `{serviceId}/{prefix}/{action}` -- e.g., `deviceWatcher/@/About`
- **Channel endpoints**: `{serviceId}/{channelId}/{prefix}/{action}` -- e.g., `deviceWatcher/cpuLoad/!/Stream`
- **Node endpoints**: the Node's own About uses `{nodeId}/@/About`, but the monitor endpoint subscribes to `+/@/About` (a wildcard that catches all direct children).

---

## 6. Services

A Service is the primary application-level component in Lynx. It represents a single program or device that connects to the broker, publishes data through Channels, and describes itself via About.

### 6.1 Service Endpoints

Every Service automatically creates three endpoints:

**`{serviceId}/@/About`** (pub, QoS 1, retained)
Publishes the full self-description on connect and whenever state changes.

**`{serviceId}/?/About`** (sub)
Receives queries. When a message arrives, the Service produces its About, optionally trims it by the `contents` parameter in the request, and publishes the result to `@/About`.

**`{serviceId}/@/Notice`** (pub, QoS 1, not retained)
Publishes log-level notices (DEBUG through CRITICAL) as structured JSON.

### 6.2 About Payload

The `@/About` payload for a Service looks like this:

```json
{
  "lynxType": "Service",
  "docs": {
    "id": "deviceWatcher",
    "title": "Device Watcher",
    "description": "Watches the device running this service and publishes statistics.",
    "lynx_version": "A-01.01",
    "time_source": "unix"
  },
  "config": {},
  "status": {
    "state": "idle",
    "action": {
      "command": "",
      "payload": {}
    }
  },
  "endpoints": {
    "deviceWatcher/@/About": {
      "endpoint_direction": "pub",
      "description": "Publish information about the Component.",
      "payload_schema": { }
    },
    "deviceWatcher/?/About": {
      "endpoint_direction": "sub",
      "description": "Query information about the Component.",
      "payload_schema": { }
    },
    "deviceWatcher/@/Notice": {
      "endpoint_direction": "pub",
      "description": "Publish a notice about the Component.",
      "payload_schema": { }
    }
  },
  "channels": {
    "cpuLoad": {
      "lynxType": "Channel",
      "docs": { "id": "cpuLoad", "title": "CPU Load", "description": "Polls the CPU load", "lynx_version": "A-01.01" },
      "config": {},
      "status": { "state": "idle", "action": { "command": "", "payload": {} } },
      "endpoints": { }
    }
  }
}
```

Key sections:

| Section | Mutability | Description |
|---------|-----------|-------------|
| `lynxType` | Immutable | Always `"Service"` for a Service. |
| `docs` | Immutable | Identity metadata: `id`, `title`, `description`, `lynx_version`, `time_source`. |
| `config` | Mutable | Runtime configuration. Application-defined. |
| `status` | Mutable | Current `state` and in-progress `action`. |
| `endpoints` | Immutable | Map of topic string to endpoint metadata (direction, schema, description). |
| `channels` | Mixed | Map of channel ID to channel About (each channel has its own docs/config/status/endpoints). |

### 6.3 Service Lifecycle

```mermaid
sequenceDiagram
    participant S as Service
    participant B as MQTT Broker

    S->>B: Set LWT: {serviceId}/@/About = {"status":{"state":"disconnected"}} (retained)
    S->>B: CONNECT
    B-->>S: CONNACK
    S->>B: SUBSCRIBE {serviceId}/#
    S->>B: PUBLISH {serviceId}/@/About (retained, QoS 1)
    Note over S,B: Service is now live and discoverable

    loop Main Loop
        S->>S: sleep(1)
    end

    Note over S,B: On unexpected disconnect:
    B->>B: Broker publishes LWT to {serviceId}/@/About
```

### 6.4 Broker Resolution

When a Service (or Node) starts, it resolves the broker address in this priority order:

1. Environment variables `UPSTREAM_NODE_HOST` / `UPSTREAM_NODE_PORT`
2. `lynxConf.json` file in the working directory (`UpstreamNodeHost` / `UpstreamNodePort`)
3. Default: `localhost:1883`

### 6.5 Python SDK Example

```python
from lynx_sdk.components.service import Service

service = Service(
    id="deviceWatcher",
    title="Device Watcher",
    description="Watches the device running this service and publishes statistics.")

# ... add channels ...

if __name__ == "__main__":
    service.start()
```

---

## 7. Channels

A Channel is the data path within a Service. It encapsulates a single input/output data stream with a standardized command interface (Poll, Stream, Stop) and structured output.

### 7.1 Channel Endpoints

Every Channel creates four endpoints under its parent Service's topic namespace:

| Endpoint | Direction | Purpose |
|----------|-----------|---------|
| `{serviceId}/{channelId}/!/Poll` | sub | Request a single sample |
| `{serviceId}/{channelId}/!/Stream` | sub | Start continuous sampling |
| `{serviceId}/{channelId}/!/Stop` | sub | Halt an active stream |
| `{serviceId}/{channelId}/<` | pub | Data output (array of timestamped samples) |

### 7.2 Poll / Stream / Stop Lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant Ch as Channel
    participant Out as {channelId}/<

    rect rgb(240, 240, 240)
        Note over C,Out: Poll (one-shot)
        C->>Ch: !/Poll {}
        Ch->>Ch: Call sample_function, yield once
        Ch->>Out: [{s: 0, ns: 0, data: {...}}]
    end

    rect rgb(230, 245, 255)
        Note over C,Out: Stream (continuous)
        C->>Ch: !/Stream {interval: 0.5, numSamples: 0, paginate: 1}
        Ch->>Ch: Set state = busy
        loop While continue_sampling() and not stopped
            Ch->>Ch: yield sample
            Ch->>Out: [{s, ns, data}]
        end
    end

    rect rgb(255, 240, 240)
        Note over C,Out: Stop
        C->>Ch: !/Stop {}
        Ch->>Ch: Set exit flag
        Ch->>Ch: Flush remaining samples
        Ch->>Ch: Set state = idle
    end
```

### 7.3 Output Format

Channel output is always a **JSON array** of sample objects:

```json
[
  {
    "s": 0,
    "ns": 0,
    "data": {
      "load": 23.5
    }
  },
  {
    "s": 1,
    "ns": 42000000,
    "data": {
      "load": 31.2
    }
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `s` | integer | Seconds elapsed since the start of the current stream/poll |
| `ns` | integer | Nanoseconds remainder (0 to 999,999,999) |
| `data` | object | The sample data, validated against the channel's `output_data_schema` |

Timestamps are **relative to the start of the current stream** (or zero for a Poll), measured via a high-resolution performance counter.

### 7.4 Stream Parameters

The `!/Stream` request payload accepts these parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `contents` | object \| boolean | `{}` (= all) | Filter which keys to include in output data (see section 4.6) |
| `interval` | number | 1.0 | Seconds between samples. The sample function can override this via `continue_sampling(default_interval=...)`. |
| `numSamples` | integer | 0 | Total samples to collect. `0` = infinite, `1` = single, `n` = exactly n. |
| `paginate` | integer | 1 | Number of samples per published message. `0` = collect all samples into one message, `n` = publish every n samples. |

### 7.5 The `contents` Filtering Mechanism

The `contents` parameter provides flexible control over what data is included in channel output and About responses. It operates recursively on the payload:

**Boolean mode:**
- `true` (or `{}`) -- include the full payload, no filtering.
- `false` -- change-of-value mode. Only include values that differ from the previous sample.

**Dict mode:**
```json
{
  "total": true,
  "percent": true,
  "used": false,
  "free": false
}
```
Select specific keys. Each key maps to its own `contents` rule (can nest dicts for deep structures). Keys set to `true` are always included; keys set to `false` use change-of-value.

**String mode (xxhash):**
```json
"a3b2c1d0"
```
The string is interpreted as an xxh32 hex digest. The payload is hashed and compared. If it matches, nothing is returned (no change). If it differs, the new hash (or the full payload) is returned.

### 7.6 The Sample Function

A Channel's data source is a **generator function** with the signature:

```python
def sample_function(request: InboundMessage, continue_sampling: Callable) -> Generator[dict, None, None]:
    while continue_sampling(default_interval=1.0):
        yield {"load": get_cpu_load()}
```

- `request` -- the original Poll or Stream message, including any parameters.
- `continue_sampling(default_interval)` -- returns `True` if the Channel should keep sampling, `False` if a Stop was received or the exit flag was set. The `default_interval` sets the sleep time between samples (overridden by the request's `interval` parameter).
- Each `yield` produces one sample that the Channel wraps in `{s, ns, data}` and publishes.

### 7.7 Python SDK Example

**Decorator style:**

```python
@service.new_channel(
    "cpuLoad",
    title="CPU Load",
    description="Polls the CPU load",
    output_data_schema={"load": {"type": "number", "unit": "%"}})
def sample_cpu_load(request, continue_sampling):
    while continue_sampling(default_interval=0.5):
        yield {"load": psutil.cpu_percent(interval=0.1)}
```

**Explicit style:**

```python
channel = Channel(
    id="memory",
    service=service,
    title="RAM Status",
    description="RAM status of the system",
    sample_function=sample_memory_status,
    output_data_schema=MEMORY_SCHEMA)

service.add_channel(channel)
```

---

## 8. Nodes

A Node is a broker-adjacent component that monitors the Lynx network. It tracks which Services are connected, their status, and the status of their Channels. Nodes form the topology layer of Lynx.

### 8.1 Node Endpoints

A Node creates these endpoints:

| Endpoint | Direction | Purpose |
|----------|-----------|---------|
| `{nodeId}/@/About` | pub | Node self-description (retained) |
| `{nodeId}/?/About` | sub | Query node info |
| `{nodeId}/@/Notice` | pub | Log/alert messages |
| `+/@/About` | sub | Wildcard monitor: catch About messages from all direct children |

The `+/@/About` subscription uses the MQTT `+` single-level wildcard to match any component ID at one topic level. This means a Node sees the About messages of all Services and child Nodes connected to the same broker.

### 8.2 Node About Payload

A Node's About extends the base About with `services` and `child_nodes`:

```json
{
  "lynxType": "Node",
  "docs": {
    "id": "edgeNode01",
    "title": "Edge Node 01",
    "description": "Monitors sensors on floor 3.",
    "lynx_version": "A-01.01",
    "time_source": "unix"
  },
  "config": {},
  "status": {
    "state": "idle",
    "action": { "command": "", "payload": {} }
  },
  "endpoints": { },
  "services": {
    "deviceWatcher": {
      "lynxType": "Service",
      "docs": { },
      "status": { "state": "idle" },
      "channels": { }
    }
  },
  "child_nodes": {}
}
```

The `services` and `child_nodes` maps are populated automatically as the Node receives About messages on `+/@/About`.

### 8.3 Multi-Node Topology

Nodes can be nested. A parent Node can track child Nodes, each of which tracks their own Services:

```mermaid
graph TD
    ParentNode["Parent Node (cloud)"]
    ChildNode1["Child Node (edge-1)"]
    ChildNode2["Child Node (edge-2)"]
    ServiceA["Service A"]
    ServiceB["Service B"]
    ServiceC["Service C"]

    ParentNode --- ChildNode1
    ParentNode --- ChildNode2
    ChildNode1 --- ServiceA
    ChildNode1 --- ServiceB
    ChildNode2 --- ServiceC
```

Each Node maintains a **NetworkState** -- a hierarchical in-memory model of the network tree beneath it:

```json
{
  "services": {
    "serviceA": { "lynxType": "Service", "status": { "state": "idle" }, "channels": {} },
    "serviceB": { "lynxType": "Service", "status": { "state": "busy" }, "channels": {} }
  },
  "childNodes": {
    "childNode1": {
      "services": { },
      "childNodes": { }
    }
  }
}
```

### 8.4 Python SDK Example

```python
from lynx_sdk.components.node import Node

node = Node(
    id="exampleNode",
    title="Example Node",
    description="Example Node for Lynx.",
    lynx_version="A-01.01")

if __name__ == "__main__":
    node.start()
```

---

## 9. Timestamps

Lynx uses two distinct timestamp mechanisms that serve different purposes.

### 9.1 MQTT v5 User Properties (Publish-Time Stamps)

Every message published by a Lynx component includes MQTT v5 User Properties `s` (seconds) and `ns` (nanoseconds) recording when the message was published according to the component's TimeSource.

These properties are set at the MQTT protocol level and are available on *every* Lynx message (About, Notice, Channel output, etc.).

```
MQTT v5 User Properties:
  s  = "1716580000"
  ns = "123456789"
```

### 9.2 Channel Sample Timestamps (Stream-Relative)

Inside a Channel's output array, each sample carries its own `s` and `ns` fields. These are **relative to the start of the current stream**, measured using a high-resolution performance counter (`time.perf_counter_ns()`).

```json
[
  { "s": 0, "ns": 0,         "data": { "load": 12.3 } },
  { "s": 0, "ns": 500000000, "data": { "load": 14.1 } },
  { "s": 1, "ns": 0,         "data": { "load": 13.7 } }
]
```

This means:
- Sample 1 was taken at stream start (t=0).
- Sample 2 was taken 500ms after stream start.
- Sample 3 was taken 1 second after stream start.

For a Poll, both `s` and `ns` are always `0` (single sample, no relative offset).

### 9.3 TimeSource Variants

| TimeSource | Epoch | Use Case |
|------------|-------|----------|
| `UnixTimeSource` | 1970-01-01 | Standard systems (Linux, Windows, macOS). Uses `time.time_ns()`. |
| `Epoch2000TimeSource` | 2000-01-01 | MicroPython devices where `time.time()` starts at year 2000. Adds the epoch delta automatically. |
| `ProcessPerfTimeSource` | Process start | Devices with no real-time clock. Uses `time.perf_counter_ns()` relative to process start. |

The SDK automatically selects the appropriate TimeSource by checking `time.gmtime(0)`:
- Year 1970 -> `UnixTimeSource`
- Year 2000 -> `Epoch2000TimeSource`
- Other -> `ProcessPerfTimeSource`

---

## 10. Discovery and Network State

### 10.1 Retained About as a Service Registry

When a Service connects, it publishes its full About payload to `{serviceId}/@/About` with `retain=True` and `QoS=1`. This means:

- Any client that subscribes to `{serviceId}/@/About` or `+/@/About` immediately receives the last known state, even if the Service published it hours ago.
- The broker stores exactly one retained About per Service, so the retained message store grows linearly with the number of Services.

This effectively turns the broker into a **service registry** with no additional infrastructure.

### 10.2 Querying with `?/About`

To request a fresh About (or a filtered subset), publish to `{serviceId}/?/About`:

```json
{}
```

Returns the full About. Or with `contents` filtering:

```json
{
  "contents": {
    "status": true,
    "channels": {
      "cpuLoad": {
        "status": true
      }
    }
  }
}
```

Returns only the requested subtree.

### 10.3 Discovery Flow

```mermaid
sequenceDiagram
    participant Observer as Observer / Node
    participant B as MQTT Broker
    participant S1 as Service 1
    participant S2 as Service 2

    S1->>B: PUBLISH s1/@/About (retained)
    S2->>B: PUBLISH s2/@/About (retained)

    Observer->>B: SUBSCRIBE +/@/About
    B-->>Observer: s1/@/About (retained copy)
    B-->>Observer: s2/@/About (retained copy)

    Note over Observer: Observer now knows about both services

    S1->>B: PUBLISH s1/@/About (status changed)
    B-->>Observer: s1/@/About (live update)
```

### 10.4 NetworkState

Nodes (and optionally Services with `track_network_state=True`) maintain a `NetworkState` object. This is a hierarchical dict:

```json
{
  "services": {
    "deviceWatcher": { "lynxType": "Service", "docs": {}, "status": {}, "channels": {} },
    "temperatureSensor": { "lynxType": "Service", "docs": {}, "status": {}, "channels": {} }
  },
  "childNodes": {
    "edgeNode02": {
      "services": {},
      "childNodes": {}
    }
  }
}
```

Every incoming About message on `+/@/About` is parsed, and the component is placed into the appropriate branch based on its `lynxType`:

- `"Service"` (or any payload containing `channels` or `services`) -> `services[id]`
- `"Node"` (or any payload containing `childNodes`) -> `childNodes[id]`

### 10.5 Last Will and Testament (LWT)

When a Service or Node connects, it sets an MQTT Last Will:

- **Topic**: `{componentId}/@/About`
- **Payload**: `{"status":{"state":"disconnected"}}`
- **QoS**: 1
- **Retain**: true

If the client disconnects unexpectedly, the broker publishes this LWT message. NetworkState handles it as a **partial About update** -- it merges the `status` into the existing entry without replacing the full About.

When a Service goes `disconnected`, the NetworkState also **cascades** the disconnected state to all of that Service's Channels, since they are unreachable without the Service's MQTT connection.

---

## 11. Notices

Notices are Lynx's structured logging mechanism. They bridge component-level events to MQTT so that observers can monitor health and debug issues remotely.

### 11.1 Notice Payload

Published to `{componentId}/@/Notice` (QoS 1, not retained):

```json
{
  "action": "Stream",
  "severity": "WARNING",
  "message": "Channel 'cpuLoad' is not idle, ignoring stream start request.",
  "data": {}
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | string | The command or query in execution when the notice was published. Empty if not related to a specific action. |
| `severity` | string | One of: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `message` | string | Human-readable notice message. |
| `data` | object | Additional structured data. Often empty. |

### 11.2 Severity Levels

| Severity | Value | Use |
|----------|-------|-----|
| `DEBUG` | 10 | Detailed diagnostic info (connection events, endpoint handling). |
| `INFO` | 20 | General operational messages. |
| `WARNING` | 30 | Unexpected but recoverable situations (duplicate stream request, unknown topic). |
| `ERROR` | 40 | Failures that affect a single operation (payload validation failure, handler exception). |
| `CRITICAL` | 50 | System-level failures. |

### 11.3 Python Logging Bridge

In the Python SDK, the `LoggingNoticeHandler` bridges Python's standard `logging` module to MQTT notices. Any log message at INFO or above is automatically published as a Notice, with the log record's timestamp preserved in the MQTT v5 User Properties.

---

## Appendix A: JSON Schemas

### A.1 Service About (`@/About`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "lynxType": {
      "type": "string",
      "enum": ["Service"],
      "description": "The type of the Lynx Component."
    },
    "docs": {
      "type": "object",
      "properties": {
        "id": { "type": "string", "description": "Unique identifier of the Component." },
        "title": { "type": "string", "description": "Human-readable title." },
        "description": { "type": "string", "description": "Human-readable description." },
        "lynx_version": { "type": "string", "enum": ["A-01.01"], "description": "Lynx protocol version." },
        "time_source": { "type": "string", "description": "Time source type (e.g., 'unix', 'process')." }
      }
    },
    "config": {
      "type": "object",
      "description": "Mutable runtime configuration."
    },
    "status": {
      "type": "object",
      "properties": {
        "state": {
          "type": "string",
          "enum": ["idle", "busy", "disconnected", "disabled"]
        },
        "action": {
          "type": "object",
          "properties": {
            "command": { "type": "string" },
            "payload": { "type": "object" }
          }
        }
      }
    },
    "endpoints": {
      "type": "object",
      "description": "Map of topic string to endpoint metadata.",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "endpoint_direction": { "type": "string", "enum": ["sub", "pub", "pubsub"] },
          "description": { "type": "string" },
          "payload_schema": { "type": "object" }
        }
      }
    },
    "channels": {
      "type": "object",
      "description": "Map of channel ID to channel About object.",
      "additionalProperties": { "$ref": "#/definitions/channelAbout" }
    }
  },
  "definitions": {
    "channelAbout": {
      "type": "object",
      "properties": {
        "lynxType": { "type": "string", "enum": ["Channel"] },
        "docs": {
          "type": "object",
          "properties": {
            "id": { "type": "string" },
            "title": { "type": "string" },
            "description": { "type": "string" },
            "lynx_version": { "type": "string", "enum": ["A-01.01"] }
          }
        },
        "config": { "type": "object" },
        "status": {
          "type": "object",
          "properties": {
            "state": { "type": "string", "enum": ["idle", "busy", "disconnected", "disabled"] },
            "action": {
              "type": "object",
              "properties": {
                "command": { "type": "string" },
                "payload": { "type": "object" }
              }
            }
          }
        },
        "endpoints": { "type": "object" }
      }
    }
  }
}
```

### A.2 Node About (`@/About`)

Extends the Service About schema with `services` and `child_nodes`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "lynxType": { "type": "string", "enum": ["Node"] },
    "docs": {
      "type": "object",
      "properties": {
        "id": { "type": "string" },
        "title": { "type": "string" },
        "description": { "type": "string" },
        "lynx_version": { "type": "string", "enum": ["A-01.01"] },
        "time_source": { "type": "string" }
      }
    },
    "config": { "type": "object" },
    "status": {
      "type": "object",
      "properties": {
        "state": { "type": "string", "enum": ["idle", "busy", "disconnected", "disabled"] },
        "action": {
          "type": "object",
          "properties": {
            "command": { "type": "string" },
            "payload": { "type": "object" }
          }
        }
      }
    },
    "endpoints": { "type": "object" },
    "services": {
      "type": "object",
      "description": "Map of service ID to service About object."
    },
    "child_nodes": {
      "type": "object",
      "description": "Map of child node ID to node About object (recursive)."
    }
  }
}
```

### A.3 Notice (`@/Notice`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "description": "The command or query in execution when the notice was published."
    },
    "severity": {
      "type": "string",
      "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    },
    "message": {
      "type": "string",
      "description": "Human-readable notice message."
    },
    "data": {
      "type": "object",
      "description": "Additional structured data."
    }
  }
}
```

### A.4 Poll Request (`!/Poll`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "contents": {
      "type": ["object", "boolean"],
      "default": {},
      "description": "Filter which keys to include in output data."
    }
  }
}
```

### A.5 Stream Request (`!/Stream`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "contents": {
      "type": ["object", "boolean"],
      "default": {},
      "description": "Filter which keys to include in output data."
    },
    "interval": {
      "type": "number",
      "default": 1.0,
      "minimum": 0,
      "description": "Seconds between samples."
    },
    "numSamples": {
      "type": "integer",
      "default": 0,
      "minimum": 0,
      "description": "Total samples to collect. 0 = infinite."
    },
    "paginate": {
      "type": "integer",
      "default": 1,
      "minimum": 0,
      "description": "Samples per published message. 0 = all in one message."
    }
  }
}
```

### A.6 Stop Request (`!/Stop`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {},
  "description": "Empty payload. Signals the channel to stop."
}
```

### A.7 Channel Output (`<`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "array",
  "items": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "s": {
        "type": "integer",
        "description": "Seconds since the start of the current stream."
      },
      "ns": {
        "type": "integer",
        "description": "Nanoseconds remainder (0 to 999,999,999)."
      },
      "data": {
        "type": "object",
        "description": "The sample data. Schema defined per-channel."
      }
    }
  }
}
```

---

## Appendix B: Protocol Version History

| Version | Status | Notes |
|---------|--------|-------|
| `A-01.01` | Current | Initial protocol version. Defines Services, Channels, Nodes, About, Notice, contents filtering, and the topic naming conventions described in this document. |
