# Device Watcher

Watches the device running this service and publishes statistics.

| Property | Value |
|----------|-------|
| ID | `deviceWatcher` |
| Lynx Version | A2.1 |
| Time Source | unix |

---

## Service Endpoints


<details markdown="1">
<summary><code>deviceWatcher/@/About</code> — pub</summary>

> Publish information about the Component.


- `lynxType` **string** — The type of the Lynx Component.  
  `enum: Node,Service,Channel`
- `docs` **object** — Docs cover the immutable metadata of the Component.
    - `id` **string** — The unique identifier of the Component.
    - `title` **string** — The readable title of the Component.
    - `description` **string** — The description of the Component.
    - `lynx_version` **string** — The Lynx protocol version used by the Component.  
      `enum: A2.1`
- `config` **object** — Config covers the mutable configuration of the Component.
- `status` **object** — Status covers the mutable status of the Component. Shape varies by component type.
    - `connected` **boolean** — Whether the Service is connected to the Lynx network.
- `endpoints` **object** — Object representing all the endpoints of the Component.
- `channels` **object** — Object representing all the channels of the Component.

</details>


<details markdown="1">
<summary><code>deviceWatcher/?/About</code> — sub</summary>

> Query information about the Component.


- `contents` **object | boolean** — Omit or true for the full payload. An empty object {} selects no keys.  
  `default: True`

</details>


<details markdown="1">
<summary><code>deviceWatcher/@/Notice</code> — pub</summary>

> Publish a notice about the Component.


- `action` **string** — The command or query in execution when the notice was published. Empty if not related to a command or query.
- `severity` **string** — The severity of the notice.  
  `enum: DEBUG,INFO,WARNING,ERROR,CRITICAL`
- `message` **string** — The message of the notice.
- `data` **object** — The data of the notice. Will often be empty.

</details>


---

## Channels


### CPU Load

Polls the CPU load


<details markdown="1">
<summary><code>deviceWatcher/cpuLoad/!/Poll</code> — sub</summary>

> Produce one sample immediately.


- `contents` **object | boolean** — Omit or true for the full payload. An empty object {} selects no keys.  
  `default: True`

</details>


<details markdown="1">
<summary><code>deviceWatcher/cpuLoad/!/Stream</code> — sub</summary>

> Start streaming on the channel, emitting data when available.


- `contents` **object | boolean** — Omit or true for the full payload. An empty object {} selects no keys.  
  `default: True`
- `sampleInterval` **number** — Minimum seconds between admitted samples. Samples offered sooner are discarded. 0 = admit every sample the source offers.  
  `default: 1.0` `minimum: 0`
- `numSamples` **integer** — Total samples to admit into batches. 0 = infinite. Counts only samples admitted after rate and contents filtering.  
  `default: 0` `minimum: 0`
- `batch` **object** — Flush limits for the open batch. Omitted object or omitted fields use the field defaults.
    - `maxInterval` **number** — Max seconds an open batch may wait before publish. 0 = no time limit (no empty keepalives).  
      `default: 300` `minimum: 0`
    - `maxSamples` **integer** — Max samples per published message. 0 = no count limit.  
      `default: 1` `minimum: 0`

</details>


<details markdown="1">
<summary><code>deviceWatcher/cpuLoad/!/Stop</code> — sub</summary>

> Stop the active command on the channel.


*Empty payload*

</details>


<details markdown="1">
<summary><code>deviceWatcher/cpuLoad/<</code> — pub</summary>

> Output data from the channel. A JSON array of timestamped samples; an empty array is a valid Stream message.


- `[]` **array**
    - `s` **integer** — Seconds since the start of the current stream
    - `ns` **integer** — Nanoseconds remainder since the start of the current stream
    - `data` **object** — The data from the channel
        - `load` **number**  
          `minimum: 0` `maximum: 100` `unit: %`

</details>



### RAM Status

RAM status of the system


<details markdown="1">
<summary><code>deviceWatcher/memory/!/Poll</code> — sub</summary>

> Produce one sample immediately.


- `contents` **object | boolean** — Omit or true for the full payload. An empty object {} selects no keys.  
  `default: True`

</details>


<details markdown="1">
<summary><code>deviceWatcher/memory/!/Stream</code> — sub</summary>

> Start streaming on the channel, emitting data when available.


- `contents` **object | boolean** — Omit or true for the full payload. An empty object {} selects no keys.  
  `default: True`
- `sampleInterval` **number** — Minimum seconds between admitted samples. Samples offered sooner are discarded. 0 = admit every sample the source offers.  
  `default: 1.0` `minimum: 0`
- `numSamples` **integer** — Total samples to admit into batches. 0 = infinite. Counts only samples admitted after rate and contents filtering.  
  `default: 0` `minimum: 0`
- `batch` **object** — Flush limits for the open batch. Omitted object or omitted fields use the field defaults.
    - `maxInterval` **number** — Max seconds an open batch may wait before publish. 0 = no time limit (no empty keepalives).  
      `default: 300` `minimum: 0`
    - `maxSamples` **integer** — Max samples per published message. 0 = no count limit.  
      `default: 1` `minimum: 0`

</details>


<details markdown="1">
<summary><code>deviceWatcher/memory/!/Stop</code> — sub</summary>

> Stop the active command on the channel.


*Empty payload*

</details>


<details markdown="1">
<summary><code>deviceWatcher/memory/<</code> — pub</summary>

> Output data from the channel. A JSON array of timestamped samples; an empty array is a valid Stream message.


- `[]` **array**
    - `s` **integer** — Seconds since the start of the current stream
    - `ns` **integer** — Nanoseconds remainder since the start of the current stream
    - `data` **object** — The data from the channel
        - `total` **integer** — Total amount of RAM in bytes  
          `minimum: 0` `unit: bytes`
        - `used` **integer** — Used amount of RAM in bytes  
          `minimum: 0` `unit: bytes`
        - `free` **integer** — Free amount of RAM in bytes  
          `minimum: 0` `unit: bytes`
        - `percent` **number** — Percentage of RAM used  
          `minimum: 0` `maximum: 100` `unit: %`

</details>



### Second Alert

Simulated alert: emits once per wall-clock second.


<details markdown="1">
<summary><code>deviceWatcher/secondAlert/!/Stream</code> — sub</summary>

> Start streaming on the channel, emitting data when available.


- `contents` **object | boolean** — Omit or true for the full payload. An empty object {} selects no keys.  
  `default: True`
- `numSamples` **integer** — Total samples to admit into batches. 0 = infinite. Counts only samples admitted after rate and contents filtering.  
  `default: 0` `minimum: 0`
- `batch` **object** — Flush limits for the open batch. Omitted object or omitted fields use the field defaults.
    - `maxInterval` **number** — Max seconds an open batch may wait before publish. 0 = no time limit (no empty keepalives).  
      `default: 300` `minimum: 0`
    - `maxSamples` **integer** — Max samples per published message. 0 = no count limit.  
      `default: 1` `minimum: 0`

</details>


<details markdown="1">
<summary><code>deviceWatcher/secondAlert/!/Stop</code> — sub</summary>

> Stop the active command on the channel.


*Empty payload*

</details>


<details markdown="1">
<summary><code>deviceWatcher/secondAlert/<</code> — pub</summary>

> Output data from the channel. A JSON array of timestamped samples; an empty array is a valid Stream message.


- `[]` **array**
    - `s` **integer** — Seconds since the start of the current stream
    - `ns` **integer** — Nanoseconds remainder since the start of the current stream
    - `data` **object** — The data from the channel
        - `second` **integer** — The second of the minute  
          `unit: seconds`
        - `time` **integer** — The current time in seconds since the epoch  
          `unit: seconds`
        - `timeString` **string** — The current time as a c-time formatted string

</details>



### Random Number

Emit a random integer between 1 and 3


<details markdown="1">
<summary><code>deviceWatcher/random/!/Poll</code> — sub</summary>

> Produce one sample immediately.


- `contents` **object | boolean** — Omit or true for the full payload. An empty object {} selects no keys.  
  `default: True`

</details>


<details markdown="1">
<summary><code>deviceWatcher/random/!/Stream</code> — sub</summary>

> Start streaming on the channel, emitting data when available.


- `contents` **object | boolean** — Omit or true for the full payload. An empty object {} selects no keys.  
  `default: True`
- `sampleInterval` **number** — Minimum seconds between admitted samples. Samples offered sooner are discarded. 0 = admit every sample the source offers.  
  `default: 1.0` `minimum: 0`
- `numSamples` **integer** — Total samples to admit into batches. 0 = infinite. Counts only samples admitted after rate and contents filtering.  
  `default: 0` `minimum: 0`
- `batch` **object** — Flush limits for the open batch. Omitted object or omitted fields use the field defaults.
    - `maxInterval` **number** — Max seconds an open batch may wait before publish. 0 = no time limit (no empty keepalives).  
      `default: 300` `minimum: 0`
    - `maxSamples` **integer** — Max samples per published message. 0 = no count limit.  
      `default: 1` `minimum: 0`

</details>


<details markdown="1">
<summary><code>deviceWatcher/random/!/Stop</code> — sub</summary>

> Stop the active command on the channel.


*Empty payload*

</details>


<details markdown="1">
<summary><code>deviceWatcher/random/<</code> — pub</summary>

> Output data from the channel. A JSON array of timestamped samples; an empty array is a valid Stream message.


- `[]` **array**
    - `s` **integer** — Seconds since the start of the current stream
    - `ns` **integer** — Nanoseconds remainder since the start of the current stream
    - `data` **object** — The data from the channel
        - `number` **number** — A random integer between 1 and 3

</details>


