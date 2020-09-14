import pytest, time
import p2py

def test_file1_method1(capsys):
	"""Creating one node"""
	a = p2py.P2P_Node(1239, testing_mode=True)
	a.start()
	assert a.running,"Node creation test failed"
	time.sleep(0.2)

	"""Creating two nodes"""
	b = p2py.P2P_Node(1238, testing_mode=True)
	b.start()
	assert b.running,"Node creation test failed"
	time.sleep(0.2)

	"""Connecting two nodes"""
	c = a.connect_to_address(b.server_address)
	time.sleep(0.2)
	assert a.connections and b.connections,"Node connection test failed"

	"""Sending text message"""
	msg = {
		'type' : 'TEXT',
		'data' : 'Hello'
	}

	assert c.send_message(msg),"Message sending test failed"

	"""Sending request"""

	req = {
		'type' : 'TEST',
		'data' : 'Hello'
	}

	resp = a.request(address=b.server_address, request_msg=req)

	assert resp['data']=='Hi!'


	