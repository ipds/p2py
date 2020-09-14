import p2py,time

a = p2py.P2P_Node(1239)
a.start()
b = p2py.P2P_Node(1237)
b.start()

time.sleep(0.2)


req = {
		'type' : 'TEST',
		'data' : 'Hello'
	}

resp = a.request(address=b.server_address, request_msg=req)

print(resp)
print(a.connections)
print(b.connections)
req = {
		'type' : 'TEXT',
		'data' : 'Hello'
	}

a.send_to_address(b.server_address, req)