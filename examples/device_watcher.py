"""
Device Watcher example service.

Generative AI was used in the Creation/Modification of this file.
"""

from typing import Callable
from lynx_sdk.components.channel import Channel
from lynx_sdk.components.service import Service
from lynx_sdk.utils.mqtt_client import InboundMessage

import math
import psutil
import threading
import time

service = Service(
    id="deviceWatcher",
    title="Device Watcher",
    description="Watches the device running this service and publishes statistics.")

# -CPU Load-
@service.new_channel(
    "cpuLoad",
    title="CPU Load",
    description="Polls the CPU load",
    output_data_schema={"load": {"type": "number", "unit": "%", "minimum": 0, "maximum": 100}})
def sample_cpu_load(request: InboundMessage, continue_sampling: Callable):
    while continue_sampling(default_interval=0.5):
        yield {"load": psutil.cpu_percent(interval=0.1)}
    #TODO any exception will be caught by the Channel and published as an exception


# def sample_temperature():
#     # Check if the function is supported on the current system
#     if hasattr(psutil, "sensors_temperatures"):
#         return {"cpu_temperature": psutil.sensors_temperatures()}
#     else:
#         service.publish_exception("No temperature sensors found or supported on this system.")


# -Memory-
def sample_memory_status(request: InboundMessage, continue_sampling: Callable):
    while continue_sampling():
        mem_info = psutil.virtual_memory()
        yield {
            "total": mem_info.total,
            "used": mem_info.used,
            "free": mem_info.free,
            "percent": mem_info.percent
        }

MEMORY_CHANNEL_DATA_SCHEMA = { # to completely define the payload schema, use the output_payload_schema instead
    "total": {
        "title": "Total RAM",
        "type": "integer",
        "description": "Total amount of RAM in bytes",
        "unit": "bytes",
        "minimum": 0
    },
    "used": {
        "title": "Used RAM",
        "type": "integer",
        "description": "Used amount of RAM in bytes",
        "unit": "bytes",
        "minimum": 0
    },
    "free": {
        "title": "Free RAM",
        "type": "integer",
        "description": "Free amount of RAM in bytes",
        "unit": "bytes",
        "minimum": 0
    },
    "percent": {
        "title": "RAM Percentage",
        "type": "number",
        "description": "Percentage of RAM used",
        "unit": "%",
        "minimum": 0,
        "maximum": 100
    }
}

memory_channel = Channel(
    id="memory",
    service=service,
    title="RAM Status",
    description="RAM status of the system",
    sample_function=sample_memory_status,
    output_data_schema=MEMORY_CHANNEL_DATA_SCHEMA)


service.add_channel(memory_channel)



# -Second Alert-
SECOND_CHANNEL_DATA_SCHEMA = { # to completely define the payload schema, use the output_payload_schema instead
    "second": {
        "title": "Second",
        "type": "integer",
        "description": "The second of the minute",
        "unit": "seconds"
    },
    "time": {
        "title": "Time",
        "type": "integer",
        "description": "The current time in seconds since the epoch",
        "unit": "seconds"
    },
    "timeString": {
        "title": "Time String",
        "type": "string",
        "description": "The current time as a c-time formatted string"
    }
}

second_channel = Channel(
    id="secondAlert",
    service=service,
    title="Second Alert",
    description="Simulated alert: emits once per wall-clock second.",
    output_data_schema=SECOND_CHANNEL_DATA_SCHEMA,
    config={"streamOnStartup": False})

service.add_channel(second_channel)


def run_second_alerts(channel: Channel) -> None:
    while True:
        next_tick = math.floor(time.time()) + 1.0
        delay = next_tick - time.time()
        if delay > 0:
            time.sleep(delay)
        now = time.time()
        local = time.localtime(now)
        channel.add_sample({
            "second": local.tm_sec,
            "time": int(now),
            "timeString": time.ctime(now),
        })


#-Random Number Stream-
RANDOM_NUMBER_CHANNEL_DATA_SCHEMA = {
    "number": {
        "title": "Random Number",
        "type": "number",
        "description": "A random integer between 1 and 3"
    }
}

def random_number_stream(request: InboundMessage, continue_sampling: Callable):
    import random
    while continue_sampling(default_interval=1):
        yield {"number": random.randint(1, 3)}


service.add_channel(Channel(
    id="random",
    service=service,
    title="Random Number",
    description="Emit a random integer between 1 and 3",
    output_data_schema=RANDOM_NUMBER_CHANNEL_DATA_SCHEMA,
    sample_function=random_number_stream,
    config={"streamOnStartup": False}))


if __name__ == "__main__":
    threading.Thread(target=run_second_alerts, args=(second_channel,), daemon=True).start()
    service.start()
