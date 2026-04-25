from typing import Callable
from lynx_sdk.components.channel import Channel
from lynx_sdk.components.service import Service

import psutil
import threading

service = Service(
    id="deviceWatcher",
    title="Device Watcher",
    description="Watches the device running this service and publishes statistics.")

# -CPU Load-
@service.new_poll_channel(
    "cpu_load",
    title="CPU Load",
    description="Polls the CPU load",
    output_data_schema={"load": {"type": "number", "unit": "%"}})
def sample_cpu_load():
    return {"load": psutil.cpu_percent(interval=1)}
    #TODO any exception will be caught by the Channel and published as an exception


# def sample_temperature():
#     # Check if the function is supported on the current system
#     if hasattr(psutil, "sensors_temperatures"):
#         return {"cpu_temperature": psutil.sensors_temperatures()}
#     else:
#         service.publish_exception("No temperature sensors found or supported on this system.")


# -Memory-
def sample_memory_status():
    mem_info = psutil.virtual_memory()
    return {
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
        "unit": "bytes"
    },
    "used": {
        "title": "Used RAM",
        "type": "integer",
        "description": "Used amount of RAM in bytes",
        "unit": "bytes"
    },
    "free": {
        "title": "Free RAM",
        "type": "integer",
        "description": "Free amount of RAM in bytes",
        "unit": "bytes"
    },
    "percent": {
        "title": "RAM Percentage",
        "type": "number",
        "description": "Percentage of RAM used",
        "unit": "%"
    }
}

memory_channel = Channel(
    id="memory",
    service=service,
    title="RAM Status",
    description="RAM status of the system",
    poll_function=sample_memory_status,
    output_data_schema=MEMORY_CHANNEL_DATA_SCHEMA,
    stream_function=None)


service.add_channel(memory_channel)



# -Minute Alert-
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

def second_alert(req_payload: dict, continue_sampling: Callable):
    import time
    last_second = None
    print("Second alert started")

    while continue_sampling(interval_sec=0.01):
        current_second = time.localtime().tm_sec
        if current_second != last_second:
            data = {
                "second": current_second,
                "time": int(time.time()),
                "timeString": time.ctime()
            }
            last_second = current_second
            yield data
    
    print("Second alert stopped")


second_channel = Channel(
    id="secondAlert",
    service=service,
    title="Second Alert",
    description="Emit the time every time the second changes",
    poll_function=None,
    output_data_schema=SECOND_CHANNEL_DATA_SCHEMA,
    stream_function=second_alert,
    config={"streamOnStartup": False})

service.add_channel(second_channel)


#-Random Number Stream-
RANDOM_NUMBER_CHANNEL_DATA_SCHEMA = {
    "number": {
        "title": "Random Number",
        "type": "number",
        "description": "A random integer between 1 and 3"
    }
}

def random_number_stream(req_payload: dict, continue_sampling: Callable):
    import random
    while continue_sampling(interval_sec=1):
        yield {"number": random.randint(1, 3)}


service.add_channel(Channel(
    id="random",
    service=service,
    title="Random Number",
    description="Emit a random integer between 1 and 3",
    poll_function=None,
    output_data_schema=RANDOM_NUMBER_CHANNEL_DATA_SCHEMA,
    stream_function=random_number_stream,
    config={"streamOnStartup": False}))


if __name__ == "__main__":
    service.start()
