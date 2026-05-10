from lynx_sdk.components.node import Node

node = Node(
    id="exampleNode",
    broker_socket=("localhost", 1883),
    title="Example Node",
    description="Example Node for Lynx.",
    lynx_version="A-01.01")

if __name__ == "__main__":
    node.start()