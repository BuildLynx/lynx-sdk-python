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
    start_stream_function=None)


service.add_channel(memory_channel)



# -Minute Alert-

MINUTE_CHANNEL_DATA_SCHEMA = { # to completely define the payload schema, use the output_payload_schema instead
    "minute": {
        "title": "Minute",
        "type": "integer",
        "description": "The minute of the hour",
        "unit": "minutes"
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

def start_minute_alert(channel: Channel, queue_func: callable, exit_flag: threading.Event):
    import time
    last_minute = None
    while not exit_flag.wait(timeout=0.1):
        current_minute = time.localtime().tm_min
        if current_minute != last_minute:
            data = {
                "minute": current_minute,
                "time": int(time.time()),
                "timeString": time.ctime()
            }
            queue_func(data)
            last_minute = current_minute


minute_channel = Channel(
    id="minuteAlert",
    service=service,
    title="Minute Alert",
    description="Emit the time every time the minute changes",
    poll_function=None,
    output_data_schema=MINUTE_CHANNEL_DATA_SCHEMA,
    start_stream_function=start_minute_alert)

service.add_channel(minute_channel)


if __name__ == "__main__":
    # import json
    # import pprint
    # print(json.dumps(service.produce_about(), indent=2))
    service.start()
