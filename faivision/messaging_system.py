import zmq
class Publisher:
    def __init__(self,interface,port,n_threads=1,protocol="tcp"):
        self._context = zmq.Context(io_threads=n_threads)

        self._socket = self._context.socket(zmq.SocketType.PUB)
        self._socket.setsockopt(zmq.CONFLATE,1)
        self._socket.bind(f"{protocol}://{interface}:{port}")

    def send(self,inputs:bytes):
        self._socket.send(inputs)

    def get_socket(self):
        return self._socket    
class Subscriber:
    def __init__(self,interface,port,n_threads=1,protocol="tcp"):


        self._context = zmq.Context(n_threads)

        self._socket = self._context.socket(zmq.SocketType.SUB)
        self._socket.setsockopt(zmq.CONFLATE,1)

        self._socket.connect(f"{protocol}://{interface}:{port}")
        self._socket.subscribe("".encode())

    def get_socket(self):
        return self._socket



#test cases of socker opt:
#      Publisher   Subscriber
# case IMMEDIATE X IMMEDIATE: high latency
# case IMMediate X CONFLATE: latency is different between subsribers.
# case CONFLATE  X IMMEDIATE: high latency
# case CONFLATE  X CONFLATE: best option since it balances all subscribers and low latency.
