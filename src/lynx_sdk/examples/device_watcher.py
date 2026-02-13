from lynx_sdk.components.channel import Channel
from lynx_sdk.components.service import Service

import psutil
import logging

service = Service(
    id="device_watcher",
    title="Device Watcher",
    description="Watches the device running this service and publishes statistics.")


@service.new_poll_channel(
    "cpu_load",
    title="CPU Load",
    description="Polls the CPU load",
    output_data_schema={"load": {"type": "number", "unit": "%"}})
def sample_cpu_load():
    return {"load": psutil.cpu_percent(interval=1)}
    # any exception will be caught by the Channel and published as an exception


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    service.start()






# def sample_memory_status():
#     # Check if the function is supported on the current system
#     if hasattr(psutil, "virtual_memory()"):
#         return {"cpu_temperature": psutil.sensors_temperatures()}
#     else:
#         service.publish_exception("No temperature sensors found or supported on this system.")

# memory_channel = Channel(
#     id="memory",
#     title="RAM Status",
#     description="RAM status of the system",
#     sample_function=sample_memory_status,
#     start_stream_function=None)

# memory_channel.configs = {}
# memory_channel.output_data_schema({ # to completely define the payload schema, use the output_payload_schema instead
#     "total": {
#         "title": "Total RAM",
#         "type": "integer",
#         "description": "Total amount of RAM in bytes",
#         "unit": "bytes"
#     },
#     "used": {
#         "title": "Used RAM",
#         "type": "integer",
#         "description": "Used amount of RAM in bytes",
#         "unit": "bytes"
#     },
#     "free": {
#         "title": "Free RAM",
#         "type": "integer",
#         "description": "Free amount of RAM in bytes",
#         "unit": "bytes"
#     },
#     "percent": {
#         "title": "RAM Percentage",
#         "type": "number",
#         "description": "Percentage of RAM used",
#         "unit": "%"
#     }
# })

# service.channels.append(memory_channel)


# if __name__ == "__main__":
#     service.start()