#!/usr/bin/env python
"""
A websockets server that queries a Cosmos node to obtain:
- Block height via RPC endpoint
- Consensus data via API endpoint

Syntax:
./consensus_monitor_server.py -a <API server> -r <RPC server> -p <ws listening port>
Example:
./consensus_monitor_server.py -a api.cosmos.network -r rpc.cosmos.network -p 9090

"""
import re
import urllib.parse
import json
import argparse
import sys
import asyncio
import requests
import websockets


# Consensus monitor class
class ConsensusMonitor:
    """
    Periodically requests and parses consensus data from a Cosmos node.
    Packages the data and forwards it to all connected websockets clients.
    """
    API_ENDPOINT_VALIDATORS = '/cosmos/staking/v1beta1/validators'
    RPC_ENDPOINT_VALIDATORS = '/validators'
    RPC_ENDPOINT_ABCI_INFO = '/abci_info'
    RPC_ENDPOINT_BLOCK = '/block'
    RPC_ENDPOINT_CONSENSUS = '/consensus_state'

    def __init__(self,
                 api_server: str,
                 rpc_server: str,
                 interval_seconds: float = 1):
        self.api = api_server
        self.rpc = rpc_server
        self.interval = interval_seconds
        self.node_online = False
        self.state = {}
        self.addr_moniker_dict = {}
        self.client_websockets = []

        self.generate_addr_moniker_dict()

    def get_staking_validators(self, next_key: str = None):
        """
        Obtain the list of validators through the API server
        """
        try:
            if next_key:
                validators = (requests.get(self.api + self.API_ENDPOINT_VALIDATORS +
                                           '?pagination.key=' +
                                           urllib.parse.quote(next_key))).json()
            else:
                validators = (requests.get(self.api +
                              self.API_ENDPOINT_VALIDATORS)).json()
            return validators
        except ConnectionResetError as exc:
            print("get_staking_validators exception: ConnectionResetError", exc)
        except ConnectionRefusedError as exc:
            print('get_staking_validators exception: ConnectionRefusedError', exc)
        except ConnectionError as exc:
            print("get_staking_validators exception: ConnectionError", exc)
        except requests.exceptions.ConnectionError as exc:
            print('get_staking_validators exception: NewConnectionError', exc)
        sys.exit(0)

    def get_active_validators(self, page: int = 1):
        """
        Obtain the active validator set through the RPC server
        """
        try:
            validators = (requests.get(
                self.rpc + self.RPC_ENDPOINT_VALIDATORS+f'?page={page}')).json()['result']
            return validators
        except ConnectionResetError as exc:
            print("get_active_validators exception: ConnectionResetError", exc)
        except ConnectionRefusedError as exc:
            print('get_active_validators exception: ConnectionRefusedError', exc)
        except ConnectionError as exc:
            print("get_active_validators exception: ConnectionError", exc)
        except requests.exceptions.ConnectionError as exc:
            print('get_active_validators exception: NewConnectionError', exc)
        sys.exit(0)

    def get_version(self):
        """
        Obtain the current version through the RPC server
        """
        try:
            version = (requests.get(self.rpc + self.RPC_ENDPOINT_ABCI_INFO)
                       ).json()['result']['response']['version']
            return version
        except ConnectionResetError as exc:
            print("get_version exception: ConnectionResetError", exc)
        except ConnectionRefusedError as exc:
            print('get_version exception: ConnectionRefusedError', exc)
        except ConnectionError as exc:
            print("get_version exception: ConnectionError", exc)
        except requests.exceptions.ConnectionError as exc:
            print('get_version exception: NewConnectionError', exc)
        except TypeError as exc:
            print('get_version exception: Type Error', exc)
        return None

    def get_block_height(self):
        """
        Obtain the current block height through the RPC server
        """
        try:
            current_height = int((requests.get(self.rpc + self.RPC_ENDPOINT_BLOCK)
                                  ).json()['result']['block']['header']['height'])
            return current_height
        except ConnectionResetError as exc:
            print("get_block_height exception: ConnectionResetError", exc)
        except ConnectionRefusedError as exc:
            print('get_block_height exception: ConnectionRefusedError', exc)
        except ConnectionError as exc:
            print("get_block_height exception: ConnectionError", exc)
        except requests.exceptions.ConnectionError as exc:
            print('get_block_height exception: NewConnectionError', exc)
        except TypeError as exc:
            print('get_block_height exception: Type Error', exc)
        return None

    def get_round_state(self):
        """
        Obtain the current round state through the RPC server
        """
        try:
            # round_state = (requests.get(self.rpc + \
            # '/dump_consensus_state')).json()['result']['round_state']['votes'][0]
            round_state = (requests.get(self.rpc + self.RPC_ENDPOINT_CONSENSUS)
                           ).json()['result']['round_state']['height_vote_set'][0]
            return round_state
        except ConnectionResetError as exc:
            print("get_round_state exception: ConnectionResetError", exc)
        except ConnectionRefusedError as exc:
            print('get_round_state exception: ConnectionRefusedError', exc)
        except ConnectionError as exc:
            print("get_round_state exception: ConnectionError", exc)
        except requests.exceptions.ConnectionError as exc:
            print('get_round_state exception: NewConnectionError', exc)
        except TypeError as exc:
            print('get_round_state exception: Type Error', exc)
        return None

    def generate_addr_moniker_dict(self):
        """
        Populate the address-moniker dictionary:
        {consensus_address: moniker, ...}
        """
        # Get list of validators and their consensus pubkeys
        print("Collecting consensus addresses...")
        validators = self.get_staking_validators()
        staking_vals = validators['validators']
        next_key = (validators['pagination']['next_key'])
        while next_key:
            validators = self.get_staking_validators(next_key)
            staking_vals.extend(validators['validators'])
            next_key = validators['pagination']['next_key']
        print(f'{len(staking_vals)} validators found.')
        pubkey_moniker_dict = {val['consensus_pubkey']['key']:
                               val['description']['moniker'] for val in staking_vals}

        # Get active validator set
        print('Collecting active validators...')
        validators = self.get_active_validators()
        validator_set = validators['validators']
        validators_total = int(validators['total'])
        validators_read = int(validators['count'])
        if validators_read < validators_total:
            page = 2
            while validators_read < validators_total:
                validators = self.get_active_validators(page)
                validator_set.extend(validators['validators'])
                validators_read += int(validators['count'])
                page += 1

        print(
            f'Found {len(validator_set)} addresses in the active validator set.')
        address_pubkey_dict = {
            val['address']: val['pub_key']['value'] for val in validator_set}
        # Clip the consensus address to match the vote tally reporting length
        self.addr_moniker_dict = {
            addr[:12]: pubkey_moniker_dict[pubkey] for addr, pubkey in address_pubkey_dict.items()}

    async def update_prevotes(self, round_state: dict):
        """
        Update the state dictionary with:
        - pv_list: list of validators that have voted
        - pv_voting_power: voting power that has voted so far/total voting power
        - pv_percentage: pv_voting_power in decimal format
        """
        prevotes = round_state['prevotes']
        pv_bit_array = round_state['prevotes_bit_array']
        pv_checklist = re.findall(r':[_x]+', pv_bit_array)[0][1:]
        pv_validators_voted = pv_checklist.count('x')
        pv_votes_in = int(re.findall(r'\d+/', pv_bit_array)[0][:-1])
        total_voting_power = int(re.findall(r'/\d+', pv_bit_array)[0][1:])
        pv_percentage = pv_votes_in/total_voting_power
        self.state['pv_list'] = []
        self.state['pv_percentage'] = '0.00%'
        self.state['pv_voting_power'] = f'0/{total_voting_power}'

        if pv_validators_voted > 0:
            prevotes_list = []
            for prevote in prevotes:
                if prevote != 'nil-Vote':
                    # consensus address is clipped to 12 characters
                    addr = prevote.split(':')[1].split(' ')[0]
                    try:
                        moniker = self.addr_moniker_dict[addr]
                        if moniker not in prevotes_list:
                            prevotes_list.append(moniker)
                    except KeyError as exc:
                        print("Validator address not found: ", exc)
            self.state['pv_list'] = prevotes_list
            self.state['pv_percentage'] = f'{pv_percentage:.2f}%'
            self.state['pv_voting_power'] = f'{pv_votes_in}/{total_voting_power}'

    async def update_precommits(self, round_state: dict):
        """
        Update the state dictionary with:
        - pc_list: list of validators that have voted
        - pc_voting_power: voting power that has voted so far/total voting power
        - pc_percentage: pv_voting_power in decimal format
        """
        # Precommits
        precommits = round_state['precommits']
        pc_bit_array = round_state['precommits_bit_array']
        pc_checklist = re.findall(r':[_x]+', pc_bit_array)[0][1:]
        pc_validators_voted = pc_checklist.count('x')
        pc_votes_in = int(re.findall(r'\d+/', pc_bit_array)[0][:-1])
        total_voting_power = int(re.findall(r'/\d+', pc_bit_array)[0][1:])
        pc_percentage = pc_votes_in/total_voting_power
        self.state['pc_list'] = []
        self.state['pc_percentage'] = '0.00%'
        self.state['pc_voting_power'] = f'0/{total_voting_power}'

        if pc_validators_voted > 0:
            precommits_list = []
            for precommit in precommits:
                if precommit != 'nil-Vote':
                    # consensus address is clipped to 12 characters
                    addr = precommit.split(':')[1].split(' ')[0]
                    try:
                        moniker = self.addr_moniker_dict[addr]
                        if moniker not in precommits_list:
                            precommits_list.append(moniker)
                    except KeyError as exc:
                        print("Validator address not found: ", exc)

            self.state['pc_list'] = precommits_list
            self.state['pc_percentage'] = f'{pc_percentage:.2f}%'
            self.state['pc_voting_power'] = f'{pc_votes_in}/{total_voting_power}'

    async def update_state(self):
        """
        Update the state to be broadcast to websockets clients
        The state dictionary includes:
        - block height
        - vote stats for prevotes and precommits
        """
        self.state = {}
        version = self.get_version()
        if version:
            self.state['version'] = version
            if not self.node_online:
                print('Node is online')
                self.node_online = True
        else:
            self.state['msg'] = 'Could not obtain version'
            if self.node_online:
                print('Node is offline')
                self.node_online = False
            return

        current_height = self.get_block_height()
        if current_height:
            self.state['height'] = current_height
            if not self.node_online:
                print('Node is online')
                self.node_online = True
        else:
            self.state['msg'] = 'Could not obtain block height'
            if self.node_online:
                print('Node is offline')
                self.node_online = False
            return

        round_state = self.get_round_state()
        if round_state:
            await self.update_prevotes(round_state)
            await self.update_precommits(round_state)
            if not self.node_online:
                print('Node is online')
                self.node_online = True
        else:
            self.state['msg'] = 'Could not obtain round state'
            if self.node_online:
                print('Node is offline')
                self.node_online = False
            return

    async def add_client(self, websocket):
        """
        Register websocket client, send current state
        """
        self.client_websockets.append(websocket)
        await websocket.send(json.dumps(self.state))

    async def remove_client(self, websocket):
        """
        Unregister websocket client
        """
        self.client_websockets.remove(websocket)

    async def monitor(self):
        """
        Update the consensus state and broadcast every self.interval seconds
        """
        while True:
            await self.update_state()
            for client in self.client_websockets:
                await client.send(json.dumps(self.state))
            if self.node_online:
                await asyncio.sleep(self.interval)
            else:
                await asyncio.sleep(10)


class ConsensusMonitorServer:
    """
    Websockets server for monitoring the Cosmos consensus state
    Must specify:
    - API server (including port)
    - RPC server (including port)
    - Port for incoming websockets connections
    """

    def __init__(self, api_server: str, rpc_server, interval: str, port: int):
        self.port = port
        self.monitor = ConsensusMonitor(
            api_server=api_server, rpc_server=rpc_server, interval_seconds=float(interval))

    async def start_server(self):
        """
        Start listening for websockets connections and consensus monitoring
        """
        async with websockets.serve(self.handler, "", self.port):
            await self.monitor.monitor()
            await asyncio.Future()  # run forever

    async def handler(self, websocket):
        """
        Handle incoming and departing websockets connections
        """
        await self.monitor.add_client(websocket)
        try:
            async for message in websocket:
                data = json.loads(message)
                print(data)
        finally:
            await self.monitor.remove_client(websocket)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--api',
                        help='the API server to connect to',
                        type=str,
                        required=True)
    parser.add_argument('-r', '--rpc',
                        help='the RPC server to connect to',
                        type=str,
                        required=True)
    parser.add_argument('-i', '--interval',
                        help='the number of seconds to wait between node updates',
                        type=str,
                        default='0.1')
    parser.add_argument('-p', '--port',
                        help="the port to listen on for websockets connections",
                        nargs='?',
                        type=int,
                        default=9001)
    args = vars(parser.parse_args())
    ms = ConsensusMonitorServer(
        api_server=args['api'],
        rpc_server=args['rpc'],
        interval=args['interval'],
        port=args['port'])
    asyncio.run(ms.start_server())
