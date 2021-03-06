import hashlib
import json
from time import time
from urllib.parse import urlparse
from uuid import uuid4
import os
from pathlib import Path
import requests
from flask import Flask, jsonify, request

from base64 import b64decode, b64encode

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5
# if Error - "pip install pipenv" -> "pipenv install"


serializebytes = lambda x : str (b64encode (x))[2:].strip('\\n').strip('\t')
deserializebytes = lambda x : str (b64decode (x))[2:].strip('\\n').strip('\t')

# @TODO move this variable to configuration
RSA_KEY_LENGTH = 1024


class Blockchain:

    # Generate a globally unique address for this node
    node_identifier = ''  # str(uuid4()).replace('-', '')
    pub_key = None
    priv_key = None

    def __init__(self):
        self.current_transactions = []
        self.chain = []
        self.nodes = set()
        self.load_config(config_path)
        # self.signing('test')
        # Create the genesis block
        self.new_block(previous_hash='1', proof=100)

    """
    #
    # Method to generate public and private key pair
    # used to sign/verify proof value
    #
    """
    def gen_keys(self):
        #
        # Generate RSA_KEY_LENGTH bit keypair
        #
        key = RSA.generate(RSA_KEY_LENGTH)
        
        
        #
        # Use DER format for key pair
        #

        #
        # Open file pointer for key pair
        #
        PKFile = open(self.node_identifier+'_privatekey', 'wb')
        PubKFile = open(self.node_identifier+'_publickey', 'wb')

        #
        # Export private and public keys
        #
        PK = key.exportKey('DER', passphrase='')
        PubK = key.publickey().exportKey('DER')

        #
        # Write exported key pair to file pointers
        #
        PKFile.write(PK)
        PubKFile.write(PubK)

        #
        # Close FP's
        #
        PKFile.close()
        PubKFile.close()

        #
        # Encode keys with base64
        #
        PubK_b64 = serializebytes(PubK)
        PK_b64 = serializebytes (PK)

        #
        # Return DER formated key pair
        #
        return PubK_b64, PK_b64

    def signing(self, data):
        print(self.priv_key)
        key = RSA.importKey(b64decode(self.priv_key))
        h = SHA256.new()
        h.update(data.to_bytes(255, byteorder='little'))
        signature = PKCS1_v1_5.new(key).sign(h)
        return signature

        #print(PKCS1_v1_5.new(pubkey).verify(h, signature))
        # Отличающийся хэш не должен проходить проверку
        # pkcs1_15.new(pubkey).verify(SHA256.new(b'test'), signature) # raise ValueError("Invalid signature")

    def load_config(self, c_path):
        exists = os.path.isfile(c_path)
        if not exists:
            # Store configuration file values d11589d93e7d4ba1a9e31844e6035734
            print("Config file does not exists!")
        else:
            # Keep presets
            conf = open(c_path, 'r').read()
            w_path = Path(c_path)
            if conf == "":
                print("Config file is clear.")
                return
            # print(conf)
            json_str = json.loads(conf)
            # print(json_str)
            nodes = json_str.get('nodes')

            if (json_str.get('uid') == ''):
                self.node_identifier = str(uuid4()).replace('-', '')
                json_str['uid'] = self.node_identifier
                w_path.write_text(json.dumps(
                    json_str, sort_keys=False, indent=4, separators=(',', ': ')), encoding='utf-8')
            else:
                self.node_identifier = json_str.get('uid')
            print("Node id is: "+self.node_identifier)

            if (json_str.get('pub_key') == ''):
                #
                # Тут вызов процедуры генерации ключей
                #
                self.pub_key, self.priv_key = self.gen_keys()
                json_str['pub_key'] = self.pub_key
                w_path.write_text(
                  json.dumps (
                    json_str,
                    sort_keys=False,
                    indent=4,
                    separators=(',', ': ')
                    ),
                  encoding='utf-8'
                  )
            else:
                PK = open (self.node_identifier+'_privatekey', 'rb')
                self.pub_key = json_str.get('pub_key')
                self.priv_key = serializebytes(PK.read())
                # print(self.pub_key)
                # print(self.priv_key)
            #print("Public key is: ",self.pub_key)

            # print(node_identifier)
            for node in nodes:
                # print(node)#Debug
                parsed_url = urlparse(node['address'])
                if parsed_url.netloc:
                    self.nodes.add(parsed_url.netloc)
                elif parsed_url.path:
                    # Accepts an URL without scheme like '192.168.0.5:5000'.
                    self.nodes.add(parsed_url.path)
                else:
                    raise ValueError('Invalid URL')
            print("Loaded nodes from config file ("+c_path+"): ")
            print(self.nodes)

    def register_node(self, address):
        """
        Add a new node to the list of nodes

        :param address: Address of node. Eg. 'http://192.168.0.5:5000'
        """

        parsed_url = urlparse(address)
        if parsed_url.netloc:
            self.nodes.add(parsed_url.netloc)
        elif parsed_url.path:
            # Accepts an URL without scheme like '192.168.0.5:5000'.
            self.nodes.add(parsed_url.path)
        else:
            raise ValueError('Invalid URL')

    def valid_chain(self, chain):
        """
        Determine if a given blockchain is valid

        :param chain: A blockchain
        :return: True if valid, False if not
        """

        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n-----------\n")
            # Check that the hash of the block is correct
            last_block_hash = self.hash(last_block)
            if block['previous_hash'] != last_block_hash:
                return False

            # Check that the Proof of Work is correct
            if not self.valid_proof(last_block['proof'], block['proof'], last_block_hash):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        This is our consensus algorithm, it resolves conflicts
        by replacing our chain with the longest one in the network.

        :return: True if our chain was replaced, False if not
        """

        neighbours = self.nodes
        new_chain = None

        # We're only looking for chains longer than ours
        max_length = len(self.chain)

        # Grab and verify the chains from all the nodes in our network
        for node in neighbours:
            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # Check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # Replace our chain if we discovered a new, valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True

        return False

    def new_block(self, proof, previous_hash):
        """
        Create a new Block in the Blockchain

        :param proof: The proof given by the Proof of Work algorithm
        :param previous_hash: Hash of previous Block
        :return: New Block
        """

        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }

        # Reset the current list of transactions
        self.current_transactions = []

        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        """
        Creates a new transaction to go into the next mined Block

        :param sender: Address of the Sender
        :param recipient: Address of the Recipient
        :param amount: Amount
        :return: The index of the Block that will hold this transaction
        """
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })

        return self.last_block['index'] + 1

    @property
    def last_block(self):
        return self.chain[-1]

    @staticmethod
    def hash(block):
        """
        Creates a SHA-256 hash of a Block

        :param block: Block
        """

        # We must make sure that the Dictionary is Ordered, or we'll have inconsistent hashes
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def proof_of_work(self, last_block):
        """
        Simple Proof of Work Algorithm:

         - Find a number p' such that hash(pp') contains leading 4 zeroes
         - Where p is the previous proof, and p' is the new proof

        :param last_block: <dict> last Block
        :return: <int>
        """

        last_proof = last_block['proof']
        last_hash = self.hash(last_block)

        proof = 0
        while self.valid_proof(last_proof, proof, last_hash) is False:
            proof += 1

        return proof

    def proof_check(self, proof):

        signature = self.signing(proof)

        #
        # Encode signature with base64
        #
        signature = serializebytes(signature)
        print (self.pub_key)
        request = {
            'proof': proof,
            'sign': signature,
            'pub_key' : self.pub_key,
            'uid': self.node_identifier
        }
        # print(request)
        # print(type(signature))
        #headers = {'Content-type': 'application/json'}
        for node in self.nodes:
            # print(node)
            # , headers=headers)
            r = requests.post(
                'http://'+node+'/nodes/proof_verify', json=request)
            print('Response: ' + r.text)

        return True

    @staticmethod
    def valid_proof(last_proof, proof, last_hash):
        """
        Validates the Proof

        :param last_proof: <int> Previous Proof
        :param proof: <int> Current Proof
        :param last_hash: <str> The hash of the Previous Block
        :return: <bool> True if correct, False if not.

        """

        guess = f'{last_proof}{proof}{last_hash}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:5] == "00000"


# Instantiate the Node
app = Flask(__name__)


@app.route('/mine', methods=['GET'])
def mine():
    # We run the proof of work algorithm to get the next proof...
    last_block = blockchain.last_block
    proof = blockchain.proof_of_work(last_block)

    blockchain.proof_check(proof)
    # send proof to another nodes

    # We must receive a reward for finding the proof.
    # The sender is "0" to signify that this node has mined a new coin.
    blockchain.new_transaction(
        sender="0",
        recipient=blockchain.node_identifier,
        amount=1,
    )

    # Forge the new Block by adding it to the chain
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }
    return jsonify(response), 200


@app.route('/info', methods=['GET'])
def get_info():
    response = {
        'uid': blockchain.node_identifier,
        'key': blockchain.pub_key.exportKey('PEM').decode('UTF-8')
    }
    return jsonify(response), 200


@app.route('/nodes/proof_verify', methods=['POST'])
def proof_verify():
    values = request.get_json()

    print(values)

    proof = values.get('proof')

    print("debug")

    print(values.get('sign'))

    print("---")

    sign = b64decode(values.get('sign'))

    uid = values.get('uid')
    publ_key = b64decode(values.get('pub_key'))

    """
    conf = open(config_path, 'r').read()
    json_str = json.loads(conf)
    nodes = json_str.get('nodes')

    for node in nodes:
        if (node['uid'] == uid):
            publ_key = node['pub_key']
            break
    """

    print(publ_key)
    # print(RSA.importKey(publ_key))

    h = SHA256.new()
    bytes_proof = proof.to_bytes(255, byteorder='little')
    h.update(bytes_proof)
    print('sign checking')
    key = RSA.importKey(publ_key)
    #print (key.publickey() )
    print(PKCS1_v1_5.new(key).verify(h, sign))
    print('sign checking_ok')

    # Check received proof
    last_block = blockchain.last_block
    if blockchain.valid_proof(last_block['proof'], proof, blockchain.hash(last_block)):
        # все четко
        return str(1), 200
    else:
        # проблемс
        return str(0), 200


@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()

    # Check that the required fields are in the POST'ed data
    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return 'Missing values', 400

    # Create a new Transaction
    index = blockchain.new_transaction(
        values['sender'], values['recipient'], values['amount'])

    response = {'message': f'Transaction will be added to Block {index}'}
    return jsonify(response), 201


@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200


@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()

    nodes = values.get('nodes')
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 201


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200


config_path = ''
# Generate a globally unique address for this node
# node_identifier = '098'#str(uuid4()).replace('-', '')
#pub_key = '987'

if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000,
                        type=int, help='port to listen on')
    parser.add_argument('-c', '--config', default='test_conf.txt',
                        type=str, help='path to config file')
    args = parser.parse_args()
    port = args.port
    #conf_path = args.config
    config_path = args.config
    #print("Node id is: "+node_identifier)
    Error = True
    while(Error):
        try:
            Error = False
            # Instantiate the Blockchain
            blockchain = Blockchain()
            app.run(host='0.0.0.0', port=port)
        except OSError:
            Error = True
            port = port + 1
