# Device Watcher

Watches the device running this service and publishes statistics.

| Property | Value |
|----------|-------|
| ID | `deviceWatcher` |
| Lynx Version | A2.0 |
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
      `enum: A2.0`
- `config` **object** — Config covers the mutable configuration of the Component.
- `status` **object** — Status covers the mutable status of the Component.
    - `state` **string** — The state of the Component.  
      `enum: idle,busy,disconnected,disabled`
    - `action` **object** — The currently executing command or query on the Channel.
        - `command` **string** — The command of the action.
        - `payload` **object** — The payload of the action.
- `endpoints` **object** — Object representing all the endpoints of the Component.
- `channels` **object** — Object representing all the channels of the Component.

</details>


<details markdown="1">
<summary><code>deviceWatcher/?/About</code> — sub</summary>

> Query information about the Component.


- `contents` **object | boolean** — Refer to Lynx standard contents argument for details.  
  `default: {}`

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

> Start polling at a set time interval on the channel for data.


- `contents` **object | boolean** — Default everything to true if empty  
  `default: {}`

</details>


<details markdown="1">
<summary><code>deviceWatcher/cpuLoad/!/Stream</code> — sub</summary>

> Start streaming on the channel, emitting data when available.


- `contents` **object | boolean** — Default everything to true if empty  
  `default: {}`
- `interval` **number** — Seconds between samples  
  `default: 1.0` `minimum: 0`
- `numSamples` **integer** — 1 for single, 0 for infinite, positive int for numbered, default 0  
  `default: 0` `minimum: 0`
- `paginate` **integer** — 0 for no pagination (all data in one payload), positive int for page size, default 1  
  `default: 1` `minimum: 0`

</details>


<details markdown="1">
<summary><code>deviceWatcher/cpuLoad/!/Stop</code> — sub</summary>

> Stop polling or streaming on the channel.


*Empty payload*

</details>


<details markdown="1">
<summary><code>deviceWatcher/cpuLoad/<</code> — pub</summary>

> Output data from the channel.


- `[]` **array**
    - `s` **integer** — Seconds since the start of the channel
    - `ns` **integer** — Nanoseconds since the start of the channel
    - `data` **object** — The data from the channel
        - `load` **number**  
          `unit: %`

</details>



### RAM Status

RAM status of the system


<details markdown="1">
<summary><code>deviceWatcher/memory/!/Poll</code> — sub</summary>

> Start polling at a set time interval on the channel for data.


- `contents` **object | boolean** — Default everything to true if empty  
  `default: {}`

</details>


<details markdown="1">
<summary><code>deviceWatcher/memory/!/Stream</code> — sub</summary>

> Start streaming on the channel, emitting data when available.


- `contents` **object | boolean** — Default everything to true if empty  
  `default: {}`
- `interval` **number** — Seconds between samples  
  `default: 1.0` `minimum: 0`
- `numSamples` **integer** — 1 for single, 0 for infinite, positive int for numbered, default 0  
  `default: 0` `minimum: 0`
- `paginate` **integer** — 0 for no pagination (all data in one payload), positive int for page size, default 1  
  `default: 1` `minimum: 0`

</details>


<details markdown="1">
<summary><code>deviceWatcher/memory/!/Stop</code> — sub</summary>

> Stop polling or streaming on the channel.


*Empty payload*

</details>


<details markdown="1">
<summary><code>deviceWatcher/memory/<</code> — pub</summary>

> Output data from the channel.


- `[]` **array**
    - `s` **integer** — Seconds since the start of the channel
    - `ns` **integer** — Nanoseconds since the start of the channel
    - `data` **object** — The data from the channel
        - `total` **integer** — Total amount of RAM in bytes  
          `unit: bytes`
        - `used` **integer** — Used amount of RAM in bytes  
          `unit: bytes`
        - `free` **integer** — Free amount of RAM in bytes  
          `unit: bytes`
        - `percent` **number** — Percentage of RAM used  
          `unit: %`

</details>



### Second Alert

Emit the time every time the second changes


<details markdown="1">
<summary><code>deviceWatcher/secondAlert/!/Poll</code> — sub</summary>

> Start polling at a set time interval on the channel for data.


- `contents` **object | boolean** — Default everything to true if empty  
  `default: {}`

</details>


<details markdown="1">
<summary><code>deviceWatcher/secondAlert/!/Stream</code> — sub</summary>

> Start streaming on the channel, emitting data when available.


- `contents` **object | boolean** — Default everything to true if empty  
  `default: {}`
- `interval` **number** — Seconds between samples  
  `default: 1.0` `minimum: 0`
- `numSamples` **integer** — 1 for single, 0 for infinite, positive int for numbered, default 0  
  `default: 0` `minimum: 0`
- `paginate` **integer** — 0 for no pagination (all data in one payload), positive int for page size, default 1  
  `default: 1` `minimum: 0`

</details>


<details markdown="1">
<summary><code>deviceWatcher/secondAlert/!/Stop</code> — sub</summary>

> Stop polling or streaming on the channel.


*Empty payload*

</details>


<details markdown="1">
<summary><code>deviceWatcher/secondAlert/<</code> — pub</summary>

> Output data from the channel.


- `[]` **array**
    - `s` **integer** — Seconds since the start of the channel
    - `ns` **integer** — Nanoseconds since the start of the channel
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

> Start polling at a set time interval on the channel for data.


- `contents` **object | boolean** — Default everything to true if empty  
  `default: {}`

</details>


<details markdown="1">
<summary><code>deviceWatcher/random/!/Stream</code> — sub</summary>

> Start streaming on the channel, emitting data when available.


- `contents` **object | boolean** — Default everything to true if empty  
  `default: {}`
- `interval` **number** — Seconds between samples  
  `default: 1.0` `minimum: 0`
- `numSamples` **integer** — 1 for single, 0 for infinite, positive int for numbered, default 0  
  `default: 0` `minimum: 0`
- `paginate` **integer** — 0 for no pagination (all data in one payload), positive int for page size, default 1  
  `default: 1` `minimum: 0`

</details>


<details markdown="1">
<summary><code>deviceWatcher/random/!/Stop</code> — sub</summary>

> Stop polling or streaming on the channel.


*Empty payload*

</details>


<details markdown="1">
<summary><code>deviceWatcher/random/<</code> — pub</summary>

> Output data from the channel.


- `[]` **array**
    - `s` **integer** — Seconds since the start of the channel
    - `ns` **integer** — Nanoseconds since the start of the channel
    - `data` **object** — The data from the channel
        - `number` **number** — A random integer between 1 and 3

</details>


