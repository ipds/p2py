What is p2py

It's a simple peer to peer networking library based on Chord made for IPDS project. 

The goal of this project is to create a extraordinarly simple to use yet powerfull peer to peer networking library for Python. It's created for IPDS project but can be used by everyone with ease.

Why p2py?

That's why:

- It's plug-and-play,
- It's easy to use,
- It's customizable



Features

P2py is packed with many usefull features that will help you build your p2p app faster:

- TCP Hole Punching
- Chord routing system (So you can connect to other node jus using it's numeric ID)
- Temporary / constant connections
- Sending any type of data (that can be represented in bytes)
- Messages
- Requests (p2py's experimental approach that will save you some time)
- Built-in text message type
- Tools for defining and handling your own message types

Installation

Install with pip using the command:

    $ pip install p2py



Simple examples

Joining the network and sending text message

Node B joins the network of Node A

Node A (172.17.0.2:4444)  UUID 0

    import p2py, time
    
    node = p2py.Node(4444) #Create a node listening on port 4444
    node.start() #Start the node
    
    while True: #Wait forever
    	time.sleep(1) 
    	
    #Listening on 172.17.0.2:4444
    #(172.11.0.3:4444) -> "Hi!"

Node B (172.11.0.3:4445) UUID 1

    import p2py, time
    
    node = p2py.Node(4445) #Create a node listening on port 4444
    node.start() #Start the node
    
    node.join_network((('172.17.0.2', 4444))) #Join the network of Node A
    while not node.joined(): #Wait until the node joins the network
    	time.sleep(1) 
    
    msg = {	#Construct a message
        'type' : 'text',
        'data' : "Hi!"
    }
    node.send_to_UUID(UUID=0, msg=msg) #Send a message to Node A
    	
    #Listening on 172.11.0.3:4444
    #Successfully joined the network! Your UUID is 1
    #Sent message to UUID 0

Define custom request type and send request

In this example I will define a custom request type thet will add 1 to a requested number and return the result bact to requesting peer.

Node A (172.17.0.2:4444) 

    import p2py, time
    
    node = p2py.Node(4444) #Create a node listening on port 4444
    
    def handle_add(node, conn, request): #Define a handler
    	n = request.contents['data'] #Get data from request
    	n_plus_one = n + 1 #Process the data
    	resp = { #Construct a response
            'type' : 'ADD RESP',
            'data' : n_plus_one
    	}
    	request.respond(resp)  #Respond
    
    node.add_handler("ADD", handle_add) #Assign the handler to "ADD" message type
    
    node.start() #Start the node
    
    while True: #Wait forever
    	time.sleep(1) 
    	
    #Listening on 172.17.0.2:4444

Node B (172.11.0.3:4445)

    import p2py, time
    
    node = p2py.Node(4445) #Create a node listening on port 4444
    node.start() #Start the node
    
    node.join_network((('172.17.0.2', 4444))) #Join the network of Node A
    while not node.joined(): #Wait until the node joins the network
    	time.sleep(1) 
    
    msg = {	#Construct a request
        'type' : 'ADD',
        'data' : 17
    }
    resp = node.request(UUID=0, request_msg=msg) #Send a request to Node A and receive response
    result = resp['data']
    print(f"17 + 1 = {result}")
    
    
    #Listening on 172.11.0.3:4444
    #Successfully joined the network! Your UUID is 1
    #Sent message to UUID 0
    #17 + 1 = 18



Documentation

This is documentation of some high level functions (there is a lot more)

p2py.Node(port, host[opt])

Creates node object. It will listen for connections on specified port [int]. If host [str] was not specified it will run on localhost (127.0.0.1)

Example:

    example_node = Node(4444)



Functions:

Node.connect_to_network(address_list)

Connects node to network of peer which address_list [tuple] was given. Argument address_list is a list of 2-tuples of host (str) and port (int): (HOST [str], PORT [int]).

Example:

    example_node.connect_to_network([('127.0.0.1', 1234)])



Node.send_to_UUID(UUID, message)

Creates a temporary connection with UUID [Int] (that means it will be closed after sending the message) and sends message [dict].

Message is a JSON dict it this form:

    {
        'type' : MESSAGE_TYPE,
        'data' : MESSAGE_DATA
    }



Example:

    message = {
        'type' : 'TEXT',
        'data' : 'Hello!'
    }
    example_node.send_to_UUID(7, message)
    #sends hello to UUID 7



Node.send_to_address(address, message)

Creates a temporary connection with address [2-tuple] (that means it will be closed after sending the message) and sends message [dict].

Example:

    message = {
        'type' : 'TEXT',
        'data' : 'Hello!'
    }
    example_node.send_to_address(('127.0.0.1', 1234), message)
    #sends hello to 127.0.0.1:1234



Node.send_to_connection(connection, message)

Sends message [dict] to connection[Connection].

Example:

    message = {
        'type' : 'TEXT',
        'data' : 'Hello!'
    }
    conn = get_connection_object() #this is a pseudo function. Don't try it as it doesnt exist
    example_node.send_to_connection(conn, message)
    #sends hello to conn



Node.request(UUID[opt], address[opt], connection[opt], request_msg)

Sends request [Request] to UUID[Int] OR address[2-tuple] OR connection[Connection] (at least one has to be specified). It returns dict as a response or NoneType if there is no response.

The requested node receives Request object. You can learn about handling requests in this section

Example:

    request = {
        'type' : 'ADD',
        'data' : 17
    }
    
    resp = example_node.request(UUID=7, request_msg=request)
    print(f"17 + 1 = {resp['data']}")



Node.send_to_peer_book(message, exclude [opt])

Sends message [dict] to all peers in your peer book optionally excluding UUIDs[Int] in exclude [List]

Example:

    message = {
        'type' : 'TEXT',
        'data' : 'Hello peer book!'
    }
    example_node.send_to_peer_book(message)
    #sends "Hello peer book!" to peer book



Node.close_all_connections()

Closes all connections. It's synonymous to leaving the network

Example:

    example_node.close_all_connections()
    #left the network



Variables

Node.UUID [Int]

This variable holds node's UUID. It's set to None when node is not connected to any network.

Example:

    print(example_node.UUID)
    #3



Node.network_size [Int]

This variable holds info about the number of peers in the network Node is connected to

Example:

    print(example_node.network_size)
    #77



Message types

There are many types of messages that do different things. These are some high-level ones:

type TEXT

    message = {
        'type' : 'TEXT',
        'data' : text_message
    }
