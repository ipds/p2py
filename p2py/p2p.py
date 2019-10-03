'''
p2py is an official p2p networking library created for Python implementation of Interplanetary Database System (IPDS).

Copyright (C) 2019  Adam Szokalski and other authors < see https://ipds.network/authors or https://ipds.team >. All rights reserved.
Using IPDS-Python for commercial purposes requires an acknowledgment.

https://ipds.network and https://github.com/ipds/IPDS-Python
Contact: contact@ipds.team or aszokalski@ipds.team

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

'''

import socket, select, time, pickle, queue, random, string
from threading import Thread, RLock
from _thread import *
from utils.constants import *
from utils.log import init_logger

class P2P_Node:
###########################################################################################################
# CONSTRUCTOR / DESTRUCTOR ################################################################################
###########################################################################################################

    def __init__(self, port=DEFAULT_PORT, host='', rendezvous_server_address=None, testing_mode=False, allow_self_connections=False):

        if not host:
            #If host wasn't specified get it by contacting a public website
            self._init_server_host()
        else:
            self.server_host = host

        self.server_port = port

        self.server_address = (self.server_host, self.server_port)

        self.logger = init_logger(__name__, testing_mode=testing_mode, address=self.server_address)

        self.allow_self_connections = allow_self_connections

        self.message_handlers = {
            "TEXT": self.handle_text_message,
            "JOIN REQUEST": self.handle_join_request,
            "JOIN REQUEST FINALIZED": self.handle_join_request_finalized,
            "NEW PEER" : self.handle_new_peer,
            "PEER LEFT" : self.handle_peer_left,
            "UUID ADDRESS REQUEST" : self.handle_uuid_address_request,
            "UUID ADDRESS REQUEST RESPONSE" : self.handle_uuid_address_request_response,
            "CONNECTION INIT" : self.handle_connection_init
        }

        self.connections = [] #All active Connection objects

        self.connections_by_address = {} #All active Connections by their addresses

        self.peer_book = {} #Let's you access Connections by UUID

        self.peer_book_lock = RLock() #Locker for peer book

        self.my_successors = [] #list of UUIDS you add to peer book when they connect 

        self.UUID = None

        self.network_size = 1

        self.active_peers = [] #list of all UUIDs in network

        self.free_UUIDs = [] #list of disconnected  UUIDs

        self.task_queue = queue.LifoQueue() #queues messages received from peers

        self.pending_messages = {} #dict that contains messages that are waiting to be sent to given UUID

        self.pending_requests = {} #Dict that contains requests waiting for response. request_id -> response

        self.pending_uuids = {} #dict of UUIDS that wait for connection. They allso have type of the connection attached

        self.rendezvous_server_address = rendezvous_server_address #Address of rendezvous server

        #connect to rendezvous server
        self.rendezvous_server_conn = None
        if self.rendezvous_server_address:
            c = Connection(self, self.rendezvous_server_address, const=True)
            self.connections.append(c)
            self.rendezvous_server_conn = c

    def __del__(self):
        self.stop()

###########################################################################################################
# API FUNCTIONS ###########################################################################################
###########################################################################################################

    def add_handler(self, message_type, handler_function):
        self.message_handlers[message_type] = handler_function

###########################################################################################################
# HELPER FUNCTIONS ########################################################################################
###########################################################################################################

    def _init_server_host(self):
        """ Attempt to connect to an Internet host in order to determine the
        local machine's IP address.

        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("www.google.com", 80))
        self.server_host = s.getsockname()[0]
        s.close()

    def is_connected(self):
        return self.UUID != None

    def connected_to(self, UUID):
        for conn in self.connections:
            if conn.client_UUID == UUID:
                return True
        return False

    def get_next_UUID(self):
        next_node_UUID = 0
        self.peer_book_lock.acquire()
        if len(self.peer_book):
            next_node_UUID = max(self.peer_book.keys())
        self.peer_book_lock.release()
        return next_node_UUID

    def get_random_UUID(self):
        random_uuid = random.choice(self.active_peers)
        while random_uuid == self.UUID:
            random_uuid = random.choice(self.active_peers)
        return random_uuid
        
    def get_successors(self):
        ret = []

        n = 0
        while True:
            successor = self.UUID - 2**n
            if successor < 0:
                break
            ret.append(successor)
            n += 1

        n = 0
        while True:
            successor = self.UUID + 2**n
            if successor >= self.network_size:
                break
            ret.append(successor)
            n += 1
        ret.sort()
        return ret

    def get_closest_UUID_form_peer_book(self, UUID):
        self.peer_book_lock.acquire()
        ret = min(self.peer_book.keys(), key=lambda x:abs(x-UUID))
        self.peer_book_lock.release()

        return ret

###########################################################################################################
# MAIN FUNCTIONS ##########################################################################################
###########################################################################################################

    def join_network(self, address_list):
        #you need to close all connections before you join a network
        self.close_all_connections()

        for addr in address_list:
            adder_conn = self.connect_to_address(addr)
            if adder_conn:
                join_request = {
                    'type' : 'JOIN REQUEST',
                    'data' : {
                        'address' : (self.server_host, self.server_port)
                    }
                }

                if adder_conn:
                    adder_conn.send_message(join_request)
                self.logger.debug("Join request sent")
                return
                
        self.logger.error("Couldn't join the network")


    def connect_to_address(self, address, temp=False, const=False):
        if address in [(self.server_host, self.server_port), ('127.0.0.1', self.server_port), ('localhost', self.server_port)]:
            if not self.allow_self_connections:
                self.logger.warning('YOU CANT CONNECT TO YOURSELF (Unless you really need to. Set allow_self_connections to True)')
                return False
            else:
                # create a connection to self
                c = Connection(self, None, temp=temp, const=const)
                self.connections.append(c)

        if address in self.connections_by_address.keys():
            #you are already connected to that node
            return self.connections_by_address[address]

        try:
            # create a new p2p connection
            c = Connection(self, address, temp=temp, const=const)
            self.connections.append(c)
        except:
            try:
                self.logger.debug("Sending connection init request")
                msg = {
                    'type' : 'CONNECTION_INIT_REQUEST',
                    'target_address' : address
                }
                resp = self.request(connection=self.rendezvous_server_conn, request_msg=msg)
                self.logger.debug("Received response")
                return self.hole_punching(resp)
            except:
                self.logger.error(f"Couldn't connect to {address}")
                return False
        return c

    def hole_punching(self, resp):
        if resp:
            if resp['trg_address']:
                #Got the address
                (trg_public_address, trg_private_address) = resp['trg_address'] #target
                (src_public_address, src_private_address) = resp['src_address'] #you
                auth = (trg_public_address, trg_private_address)

                threads = {
                    '0_accept': Thread(target=_thrd_accept, args=(src_private_address[1], auth,)),
                    '1_accept': Thread(target=_thrd_accept, args=(src_public_address[1], auth,)),
                    '2_connect': Thread(target=_thrd_connect, args=(src_private_address, trg_public_address, auth,)),
                    '3_connect': Thread(target=_thrd_connect, args=(src_private_address, trg_private_address, auth,)),
                }

                for name in sorted(threads.keys()):
                    threads[name].start()

                while threads:
                    keys = list(threads.keys())
                    for name in keys:
                        try:
                            threads[name].join(1)
                        except TimeoutError:
                            continue
                        if not threads[name].is_alive():
                            threads.pop(name)

                self.logger.debug("Successfully connected")
                return self.connections_by_address[trg_private_address]

            else:
                self.logger.error('Address not on the network')
                return False
        else:
            self.logger.error('Rendezvous server not responding')
            return False

    def _thrd_accept(self, port, auth):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        s.bind(('', port))
        s.listen(1)
        s.settimeout(SERVER_TIMEOUT)

        i = 0
        while auth[1] not in self.connections_by_address.keys():
            try:
                conn, addr = s.accept()
            except socket.timeout:
                if i == HOLE_PUNCHING_TIMEOUT:
                    break
                i += 1
                continue
            else:
                if addr in auth:
                    c = Connection(self, addr, conn)
                    self.connections.append(c)
                    break

    def _thrd_connect(self, local_addr, addr, auth):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        s.bind(local_addr)
        i = 0
        while auth[1] not in self.connections_by_address.keys():
            try:
                s.connect(addr)
            except socket.error:
                if i == HOLE_PUNCHING_TIMEOUT:
                    break
                i += 1
                continue
            else:
                c = Connection(self, addr, s)
                self.connections.append(c)
                break

    def connect_to_UUID(self, UUID, temp=True):
        if UUID >= self.network_size:
            #desired peer doesn't exist in the network
            return False

        #Check if this peer is in your peer book
        self.peer_book_lock.acquire()
        if UUID in self.peer_book.keys():
            self.peer_book_lock.release()
            return self.peer_book[UUID]
        self.peer_book_lock.release()

        #When you don't have direct connection tho desired peer - search for it
        self.peer_book_lock.acquire()
        route = self.peer_book[self.get_closest_UUID_form_peer_book(UUID)]
        self.peer_book_lock.release()

        request = {
            'type' : 'UUID ADDRESS REQUEST',
            'data' : {
                'UUID' : UUID,
                'callback_address' : (self.server_host, self.server_port)
            }
        }
        #pass the request
        result = route.request(request)
        return self.connect_to_address(result['data']['address'])


    def close_connection(self, conn):
        if conn:
            conn.send_message({'type' : 'KILL CONNECTION'})
            conn.stop()

    def close_all_connections(self):
        for c in self.connections:
            self.close_connection(c)

    def send_to_connection(self, conn, message):
        if type(conn) is int:
            # conn is index of connection
            conn = self.connections[conn]
        if conn:
            conn.send_message(message)
            self.event_sent_message(conn.connection_address)

    def send_to_UUID(self, UUID, message):
        conn = self.connect_to_UUID(UUID)

        if conn:
            conn.send_message(message)
            self.event_sent_message(conn.connection_address)

    def send_to_address(self, address, message):
        conn = self.connect_to_address(address, temp=True)

        if conn:
            conn.send_message(message)
            self.event_sent_message(conn.connection_address)

    def request(self, request_msg, UUID=None, address=None, connection=None):
        if (UUID is not None) + (address is not None) + (connection is not None) > 1:
            raise ValueError('Expected only two arguments ([UUID or address or connection], request)')

        #make a connection
        if UUID is not None:
            #With UUID specified
            conn = self.connect_to_UUID(UUID)
        elif address is not None:
            #With address specified
            conn = self.connect_to_address(address)
        elif connection is not None:
            conn = connection
            #With connection specified
        else:
            raise ValueError('Expected two arguments ([UUID or address or connection], request)')

        result = conn.request(request_msg)

        if conn.client_UUID not in self.peer_book.keys():
            self.close_connection(conn)
        
        return result

    #OUTDATED - sending thread. It sends message when it's connected and then kills itself
    def _thrd_send_to_UUID(self, UUID, message):
        while True:
            self.peer_book_lock.acquire()
            if UUID in self.peer_book.keys():
                conn = self.peer_book[UUID]
                self.send_to_connection(conn, message)
                self.peer_book_lock.release()
                return
            self.peer_book_lock.release()
            time.sleep(SEND_MESSAGE_TIMEOUT)

    def send_to_peer_book(self, message, exclude=[]):
        self.peer_book_lock.acquire()
        for UUID, conn in self.peer_book.items():
            if UUID in exclude:
                continue
            if conn:
                conn.send_message(message)
                try:
                    self.event_sent_message(conn.connection_address)
                except:
                    pass
        self.peer_book_lock.release()
    
    def add_node(self, UUID, conn):
        self.peer_book_lock.acquire()
        self.peer_book[UUID] = conn
        self.peer_book_lock.release()

        if UUID not in self.active_peers:
            self.active_peers.append(UUID)

        if UUID in self.free_UUIDs:
            self.free_UUIDs.remove(UUID)

        try:
            self.event_new_peer_added_to_peer_book(conn.connection_address, UUID)
        except:
            pass

    def delete_node(self, UUID):
        self.peer_book_lock.acquire()
        if UUID in self.peer_book.keys():
            del self.peer_book[UUID]
            #spread the info about peer that left the network
            notif = {
                'type' : 'PEER LEFT',
                'data' : {
                    'UUID' : UUID
                }
            }
            self.send_to_peer_book(notif)
            self.event_peer_left_network(UUID)
            
            if UUID not in self.free_UUIDs:
                self.free_UUIDs.append(UUID)

        self.peer_book_lock.release()

        if UUID in self.active_peers:
            self.active_peers.remove(UUID)
            self.network_size -= 1

###########################################################################################################
# HANDLERS ################################################################################################
###########################################################################################################

    def handle_text_message(self, conn, message):
        try:
            address = conn.connection_address
        except:
            pass
        self.logger.debug(f"New message from {address[0]}:{address[1]} -> {message['data']}")

    def handle_join_request(self, conn, request):
        try:
            self.logger.debug(f"New join request from {conn.getName()}")
        except:
            pass

        #If node wasn't in any network before it becomes the first node int the network
        if self.UUID == None:
            self.UUID = 0

        next_node_UUID = self.get_next_UUID()

        if next_node_UUID <= self.UUID:
            #connect to peer (if it's already connected then return the connection object)
            conn = self.connect_to_address(tuple(request['data']['address']))

            #create initial values for new peer
            if self.free_UUIDs:
                new_node_UUID = self.free_UUIDs.pop()
            else:
                new_node_UUID = self.UUID + 1

            #Set new UUID for this connection.
            if conn:
                conn.set_UUID(new_node_UUID)

            #Adding new node to peer book.
            self.network_size += 1
            self.add_node(new_node_UUID, conn)

            #This is a response you will send to joining peer.
            resp = {
                'type' : 'JOIN REQUEST FINALIZED',
                'data' : {
                    'joiner_UUID' : new_node_UUID,
                    'adder_UUID' : self.UUID,
                    'network_size' : self.network_size,
                    'active_peers' : self.active_peers #this one may grow to large sizes. I should buffer it
                }
            }
            if conn:
                conn.send_message(resp)


            #This is a message you will send to all peers in the network 
            #to notify them about new network member.

            #self.logger.debug("Sourcing information about new peer...")

            new_peer_notif = {
                'type' : "NEW PEER",
                'data': {
                    'UUID' : new_node_UUID,
                    'Address' : conn.connection_address
                }
            }
            self.send_to_peer_book(new_peer_notif, exclude=[new_node_UUID])

            #self.logger.debug("Finished sourcing")

        else:
            self.peer_book_lock.acquire()

            if conn not in self.peer_book.values():
                self.close_connection(conn)

            next_node = self.peer_book[next_node_UUID]
            self.peer_book_lock.release()

            next_node.send_message(request)
            
            self.logger.debug("Passing node next")


    def handle_join_request_finalized(self, conn, response):

        self.UUID = response['data']['joiner_UUID']
        self.network_size = response['data']['network_size']
        self.active_peers = response['data']['active_peers']

        adder_UUID = response['data']['adder_UUID']
        
        
        #the peer who added you is your successor - add it to your peer book
        self.add_node(adder_UUID, conn)

        #update list of your successors to add them whern they connect to you
        self.my_successors = self.get_successors()

        if conn:
            conn.set_UUID(adder_UUID)
                
        self.event_joined_network()

    def handle_new_peer(self, conn, notif):
        #check if this peer is in your peer book
        self.peer_book_lock.acquire()
        if conn.client_UUID not in self.peer_book.keys():
            self.peer_book_lock.release()
            return
        self.peer_book_lock.release()

        new_peer_UUID = notif['data']['UUID']

        #check if this notification isn't going around and back to you
        if new_peer_UUID in self.active_peers:
            return

        self.active_peers.append(new_peer_UUID)

        self.send_to_peer_book(notif)



        self.network_size += 1

        if new_peer_UUID not in self.get_successors():
            #This peer shouldn't be in your peer book
            return

        new_peer_address= notif['data']['Address']


        conn = self.connect_to_address(tuple(new_peer_address))
        if conn:
            self.add_node(new_peer_UUID, conn)

    def handle_peer_left(self, conn, notif):
        #check if this peer is in your peer book
        self.peer_book_lock.acquire()
        if conn.client_UUID not in self.peer_book.keys():
            self.peer_book_lock.release()
            return
        self.peer_book_lock.release()

        left_peer_UUID = notif['data']['UUID']

        #check if this notification isn't going around and back to you
        if left_peer_UUID not in self.active_peers:
            return

        self.active_peers.remove(left_peer_UUID)

        self.send_to_peer_book(notif)

        self.delete_node(left_peer_UUID)

    def handle_uuid_address_request(self, conn, request):
        #check if this peer is in your peer book
        self.peer_book_lock.acquire()
        if conn.client_UUID not in self.peer_book.keys():
            self.peer_book_lock.release()
            return
        self.peer_book_lock.release()

        UUID = request.contents['data']['UUID']
        
        self.peer_book_lock.acquire()
        if UUID not in self.peer_book.keys():
            #You do not have this UUID in peer book pass the request further
            self.peer_book_lock.release()
            request.bounce(UUID = self.get_closest_UUID_form_peer_book(UUID))
            return

        self.peer_book_lock.release()

        #look for connection in your peer book
        self.peer_book_lock.acquire()
        UUID_address = self.peer_book[UUID].connection_address
        self.peer_book_lock.release()

        response = {
            'type' : 'UUID ADDRESS REQUEST RESPONSE',
            'data' : {
                'UUID' : UUID,
                'address' : UUID_address
            }
        }

        request.respond(response)

        self.logger.debug(f"UUID {UUID} address sent to UUID {conn.client_UUID}")
        

    #outdated
    def handle_uuid_address_request_response(self, conn, response):
        UUID = response['data']['UUID']
        address = response['data']['address']
        self.logger.debug(f"Got UUID {UUID} address: {tuple(address)} from {conn.client_UUID}")


        if UUID not in self.pending_uuids.keys():
            return

        temp = self.pending_uuids[UUID]
        del self.pending_uuids[UUID]

        c = self.connect_to_address(tuple(address), temp=temp)

        if not temp:
            self.add_node(UUID, c)

        #check if there are any pending messages to be sent to tat peer
        if UUID in self.pending_messages.keys():
            for msg in self.pending_messages[UUID]:
                self.send_to_connection(c, msg)
                self.pending_messages[UUID].remove(msg)


    def handle_closed_connection(self, conn, UUID, temp=False):
        if conn:
            try:
                address = conn.connection_address
            except:
                pass
        if UUID is not None and not temp:
            self.delete_node(UUID)
        if conn in self.connections:
            self.connections.remove(conn)
        if conn.connection_address in self.connections_by_address.keys():
            del self.connections_by_address[conn.connection_address]
        del conn


        self.event_closed_connection(address, UUID)

    def handle_connection_init(self, conn, msg):
        self.hole_punching(msg)


###########################################################################################################
# EVENTS ##################################################################################################
###########################################################################################################

    def event_sent_message(self, address):
        self.logger.debug(f"Sent message to {address[0]}:{address[1]}")

    def event_closed_connection(self, address, UUID=None):
        self.logger.debug(f"Closed connection with {address[0]}:{address[1]} ({UUID})")

    def event_established_connection(self, address):
        self.logger.debug(f"Established connection with {address[0]}:{address[1]}")

    def event_new_peer_added_to_peer_book(self, address, UUID):
        self.logger.debug(f"New peer added UUID {UUID} ({address[0]}:{address[1]})")

    def event_peer_left_network(self, UUID):
        self.logger.debug(f"Peer {UUID} left the network")

    def event_joined_network(self):
        self.logger.info(f"Successfully joined the network! Your UUID is {self.UUID}")

###########################################################################################################
# START/STOP/LOOP #########################################################################################
###########################################################################################################

    def start(self):
        self.running = True
        # Start listening for connections
        start_new_thread(self.main_loop, ())
        start_new_thread(self.task_loop, ())

    def stop(self):
        self.running = False
        self.task_queue.join()
        self.close_all_connections()

        self.logger.info("STOPPING THE SERVER")

    def task_loop(self):
        #wait for tasks and process them
        while self.running:
            try:
                #get task from queue
                task = self.task_queue.get(timeout = MESSAGE_QUEUE_TIMEOUT)
                #handle this task
                task['func'](*task['args'])
                #done
                self.task_queue.task_done()

            except queue.Empty:
                continue
            time.sleep(0.2)

    def main_loop(self):
        # Create a server socket that listens for connections
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        server_socket.bind((self.server_host, self.server_port))

        server_socket.settimeout(SERVER_TIMEOUT) 
        server_socket.listen(5)

        self.logger.info(f"Listening on {self.server_host}:{self.server_port}")

        while self.running:
            try:
                # Handle incoming connection. Create a new p2p connection
                client_socket, client_address = server_socket.accept()
                c = Connection(self, client_address, client_socket)
                self.connections.append(c)

            except KeyboardInterrupt:
                self.stop()
                continue
            except socket.timeout:
                continue
            time.sleep(0.2)
        


class Connection(Thread):
    '''
        This object is used to manage connection between two peers. 
        It runs as a separate thread
    '''
    def __init__(self, callback_node, client_address, client_socket=None, client_UUID=None, temp=False, const=False):
        Thread.__init__(self) #Start this thread.

        # Set a name of this connection.
        self.client_address = client_address

        # Set the callback node variable.
        self.callback_node = callback_node

        # Set the UUID of connected node (default is None).
        self.client_UUID = client_UUID

        # Connection lives only for the first message and response
        self.temp = False

        # Defines if the connection is killable
        self.const = const

        # Counts the nuber of messages/responses sent/received
        self.messages_counter = 0 

        #queues messages received from self
        self.self_connection_bridge = queue.LifoQueue()

        self.client_socket = None

        # Initial info you share with node you establish connection with.
        my_info = {
            'HOST' : callback_node.server_host,
            'PORT' : callback_node.server_port,
            'UUID' : callback_node.UUID
        }

        if client_address:
            # Specify the connected socket.
            if client_socket:
                # Someone connected to you.
                self.client_socket = client_socket

            else:
                # You are connecting to someone/
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                self.client_socket.connect(client_address)
                self.client_socket.settimeout(CONNECTION_TIMEOUT)

            #send initial info
            self.send_message(my_info)

            # Receive initial info from node you establish connection with.
            try:
                client_info = self.receive_message(self.client_socket.recv(HEADER_LENGTH))
            except ConnectionResetError:
                return
        else:
            client_info = my_info

        # Set the connection address.
        # It can be used to share this connection to another peer.
        self.connection_address = (client_info['HOST'], client_info['PORT'])


        #Add connection address to connected addresses
        callback_node.connections_by_address[self.connection_address] = self

        # Set client UUID
        self.client_UUID = client_info['UUID']

        #check if this uuid is your successor. If so - add it to peer book
        if client_address:
            if self.client_UUID in callback_node.my_successors and not temp:
                callback_node.add_node(self.client_UUID, self)

        # Set name of this thread (mainly for logs).
        self.setName(f"{self.connection_address[0]}:{self.connection_address[1]}")

        self.temp = temp #decides if connection is temporary (dies after one message)

        # Start the thread.
        self.running = True
        self.start()

        # Callback.
        callback_node.event_established_connection(self.connection_address)


    def get_pub_and_priv_endpoint(self):
        return (self.client_address, self.connection_address)

    def __del__(self):
        # Stop the main loop
        self.running = False

    # Main loop of this connection.
    def run(self):
        death_clock = 0

        while self.running and death_clock <= NON_PEER_BOOK_CONNECTION_LIFETIME:
            try:
                if self.client_address:
                    message = self.receive_message(self.client_socket.recv(HEADER_LENGTH))
                else:
                    message = self.self_connection_bridge.get(timeout = MESSAGE_QUEUE_TIMEOUT)
                    self.self_connection_bridge.task_done()

                if type(message) == dict:
                    message_type = message['type']

                    if message_type == "KILL CONNECTION":
                        #kill connection
                        break

                    if 'request_id' in message.keys() and message['request_id'] in self.callback_node.pending_requests.keys():
                        #this is a response
                        request_id = message['request_id']
                        del message['request_id']

                        self.callback_node.pending_requests[request_id] = message

                    #Restrictions for non UUID connections
                    elif self.client_UUID is not None or self.client_UUID is None and message_type in ["JOIN REQUEST", "JOIN REQUEST FINALIZED"]:
                        #put this message in queue
                        task = {
                            'func' : self.callback_node.message_handlers[message_type],
                            'args' : (self, message)
                        }
                        self.callback_node.task_queue.put(task)

                elif type(message) == Request:
                    message.set_node(self.callback_node)
                    message_type = message.get_contents()['type']

                    #Restrictions for non UUID connections
                    if self.client_UUID is not None or self.client_UUID is None and message_type in ["JOIN REQUEST", "JOIN REQUEST FINALIZED"]:
                        #put this message in queue
                        task = {
                            'func' : self.callback_node.message_handlers[message_type],
                            'args' : (self, message)
                        }
                        self.callback_node.task_queue.put(task)

                elif message is False:
                    break

            except socket.timeout:
                #Kill non UUID connections after some time
                if self.client_UUID == None and not self.const:
                    death_clock += 1
                continue
            except queue.Empty:
                continue
            except ConnectionResetError:
                break

            # if self.temp and self.messages_counter >= 2:
            #     #close the connection if it was only temporary and 2 messages were sent/received
            #     self.send_message({'type' : 'KILL CONNECTION'})
            #     self.callback_node.handle_closed_connection(self, self.client_UUID, self.temp)

            time.sleep(0.2)

        self.callback_node.handle_closed_connection(self, self.client_UUID, self.temp)

    # This function sends messages
    def send_message(self, message):
        pickle_message = pickle.dumps(message)
        message_header = bytes(f"{len(pickle_message):<{HEADER_LENGTH}}", "utf-8")
        bytes_message = message_header + pickle_message

        try:
            if self.client_address:
                self.client_socket.send(bytes_message)
            else:
                self.self_connection_bridge.put(message)
            return True
        except BrokenPipeError:
            return False


    # This function receives messages
    def receive_message(self, message_header):
        if message_header:
            try:
                message_length = int(str(message_header, "utf-8"))
            except ValueError:
                # Invalid header
                return None

            full_message = self.client_socket.recv(message_length)
            full_message = pickle.loads(full_message)

            return full_message
        else:
            # Connection closed
            return False

        #
        

    # This function sends requests
    def request(self, request):
        request_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        request['request_id'] = request_id
        self.callback_node.pending_requests[request_id] = None
        callback_address = (self.callback_node.server_host, self.callback_node.server_port)

        request = Request(callback_address,request)
        try:
            assert self.send_message(request)
        except:
            #error sending message
            return None

        i = 0
        while self.callback_node.pending_requests[request_id] is None:
            i += 1
            if i == REQUEST_TIMEOUT:
                #didn't get a response
                return
            time.sleep(0.2)

        result = self.callback_node.pending_requests[request_id]
        del self.callback_node.pending_requests[request_id]

        return result

    def set_UUID(self, new_UUID):
        self.client_UUID = new_UUID

        #check if this uuid is your successor. If so - add it to peer book
        if self.client_UUID is not None and self.client_UUID in self.callback_node.my_successors:
            self.callback_node.add_node(self.client_UUID, self)

    def stop(self):
        # Stop the main loop
        self.callback_node.handle_closed_connection(self, self.client_UUID, self.temp)
        self.running = False

    def close(self):
        self.stop()



class Request:
    def __init__(self, callback_address, contents):
        self.callback_address = callback_address

        self.request_id = contents['request_id']
        del contents['request_id']

        self.contents = contents

    def set_node(self, node):
        self.node = node

    def get_contents(self):
        return self.contents

    def respond(self, response):
        response['request_id'] = self.request_id
        connection = self.node.connect_to_address(self.callback_address)
        connection.send_message(response)
        if connection.client_UUID not in self.node.peer_book.keys():
            connection.stop()

    def bounce(self, address = None, UUID = None):
        if UUID is not None:
            #With UUID specified
            target = self.node.connect_to_UUID(UUID)
        elif address is not None:
            #With Address specified
            target = self.node.connect_to_address(address)
        else:
            raise ValueError('Expected one argument ([UUID or address])')
            return

        contents_copy = self.contents
        contents_copy['request_id'] = self.request_id

        target.send_message(Request(self.callback_address, contents_copy))

        if target.client_UUID not in self.node.peer_book.keys():
            target.stop()