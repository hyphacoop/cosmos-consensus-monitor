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
import logging
import sys
import asyncio
import requests
import websockets

# The maximum number of websocket .send coroutines running at once
# Larger number means more concurrent bandwidth usage, each message is ~383 bytes
# Also probably a bit more CPU usage?
MAX_CONCURRENT_SEND_COROS = 100

async def gather_limit(n, *aws, return_exceptions=False):
    """
    Like asyncio.gather but concurrency is limited to n at a time.

    Source: https://stackoverflow.com/a/61478547
    """

    semaphore = asyncio.Semaphore(n)

    async def sem_aw(aw):
        async with semaphore:
            return await aw
    return await asyncio.gather(*(sem_aw(aw) for aw in aws), return_exceptions=return_exceptions)

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
        self.node = {'api': api_server,
                     'rpc': rpc_server}
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
                validators = (requests.get(self.node['api'] + self.API_ENDPOINT_VALIDATORS +
                                           '?pagination.key=' +
                                           urllib.parse.quote(next_key))).json()
            else:
                validators = (requests.get(self.node['api'] +
                              self.API_ENDPOINT_VALIDATORS)).json()
            return validators
        except ConnectionResetError as cres:
            logging.exception(
                f'get_staking_validators> ConnectionResetError: {cres}', exc_info=False)
        except ConnectionRefusedError as cref:
            logging.exception(
                f'get_staking_validators> ConnectionRefusedError: {cref}', exc_info=False)
        except ConnectionError as cerr:
            logging.exception(
                f'get_staking_validators> ConnectionError: {cerr}', exc_info=False)
        except requests.exceptions.ConnectionError as cerr:
            logging.exception(
                f'get_staking_validators> Requests ConnectionError: {cerr}', exc_info=False)
        sys.exit(0)

    def get_active_validators(self, page: int = 1):
        """
        Obtain the active validator set through the RPC server
        """
        try:
            validators = (requests.get(
                self.node['rpc'] + self.RPC_ENDPOINT_VALIDATORS+f'?page={page}')).json()['result']
            return validators
        except ConnectionResetError as cres:
            logging.exception(
                f'get_active_validators> ConnectionResetError: {cres}', exc_info=False)
        except ConnectionRefusedError as cref:
            logging.exception(
                f'get_active_validators> ConnectionRefusedError: {cref}', exc_info=False)
        except ConnectionError as cerr:
            logging.exception(
                f'get_active_validators> ConnectionError: {cerr}', exc_info=False)
        except requests.exceptions.ConnectionError as cerr:
            logging.exception(
                f'get_active_validators> Requests ConnectionError: {cerr}', exc_info=False)
        sys.exit(0)

    def get_version(self):
        """
        Obtain the current version through the RPC server
        """
        try:
            version = (requests.get(self.node['rpc'] + self.RPC_ENDPOINT_ABCI_INFO)
                       ).json()['result']['response']['version']
            return version
        except ConnectionResetError as cres:
            logging.exception(
                f'get_version> ConnectionResetError: {cres}', exc_info=False)
        except ConnectionRefusedError as cref:
            logging.exception(
                f'get_version> ConnectionRefusedError: {cref}', exc_info=False)
        except ConnectionError as cerr:
            logging.exception(
                f'get_version> ConnectionError: {cerr}', exc_info=False)
        except requests.exceptions.ConnectionError as cerr:
            logging.exception(
                f'get_version> Requests ConnectionError: {cerr}', exc_info=False)
        except KeyError as kerr:
            logging.exception(
                f'get_version> Key Error: {kerr}', exc_info=False)
        except TypeError as terr:
            logging.exception(
                f'get_version> Type Error: {terr}', exc_info=False)
        return None

    def get_block_height(self):
        """
        Obtain the current block height through the RPC server
        """
        try:
            current_height = int((requests.get(self.node['rpc'] + self.RPC_ENDPOINT_BLOCK)
                                  ).json()['result']['block']['header']['height'])
            return current_height
        except ConnectionResetError as cres:
            logging.exception(
                f'get_block_height> ConnectionResetError: {cres}', exc_info=False)
        except ConnectionRefusedError as cref:
            logging.exception(
                f'get_block_height> ConnectionRefusedError: {cref}', exc_info=False)
        except ConnectionError as cerr:
            logging.exception(
                f'get_block_height> ConnectionError: {cerr}', exc_info=False)
        except requests.exceptions.ConnectionError as cerr:
            logging.exception(
                f'get_block_height> Requests ConnectionError: {cerr}', exc_info=False)
        except KeyError as kerr:
            logging.exception(
                f'get_block_height> Key Error: {kerr}', exc_info=False)
        except TypeError as terr:
            logging.exception(
                f'get_block_height> Type Error: {terr}', exc_info=False)
        return None

    def get_round_state(self):
        """
        Obtain the current round state through the RPC server
        """
        try:
            # round_state = (requests.get(self.node['rpc'] + \
            # '/dump_consensus_state')).json()['result']['round_state']['votes'][0]
            round_state = (requests.get(self.node['rpc'] + self.RPC_ENDPOINT_CONSENSUS)
                           ).json()['result']['round_state']['height_vote_set'][0]
            return round_state
        except ConnectionResetError as cres:
            logging.exception(
                f'get_round_state> ConnectionResetError: {cres}', exc_info=False)
        except ConnectionRefusedError as cref:
            logging.exception(
                f'get_round_state> ConnectionRefusedError: {cref}', exc_info=False)
        except ConnectionError as cerr:
            logging.exception(
                f'get_round_state> ConnectionError: {cerr}', exc_info=False)
        except requests.exceptions.ConnectionError as cerr:
            logging.exception(
                f'get_round_state> Requests ConnectionError: {cerr}', exc_info=False)
        except KeyError as kerr:
            logging.exception(
                f'get_round_state> Key Error: {kerr}', exc_info=False)
        except TypeError as terr:
            logging.exception(
                f'get_round_state> Type Error: {terr}', exc_info=False)
        return None

    def generate_addr_moniker_dict(self):
        """
        Populate the address-moniker dictionary:
        {consensus_address: moniker, ...}
        """
        # Get list of validators and their consensus pubkeys
        logging.info("Collecting consensus addresses...")
        validators = self.get_staking_validators()
        staking_vals = validators['validators']
        next_key = (validators['pagination']['next_key'])
        while next_key:
            validators = self.get_staking_validators(next_key)
            staking_vals.extend(validators['validators'])
            next_key = validators['pagination']['next_key']
        logging.info(f'{len(staking_vals)} validators found.')
        pubkey_moniker_dict = {val['consensus_pubkey']['key']:
                               val['description']['moniker'] for val in staking_vals}

        # Get active validator set
        logging.info('Collecting active validators...')
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

        logging.info(
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
        pv_percentage = 100*(pv_votes_in/total_voting_power)
        self.state['pv_list'] = [0 for i in range(len(self.addr_moniker_dict))]
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
                    except KeyError as kerr:
                        logging.exception(
                            f'PV> Validator address not found: {kerr}', exc_info=False)
            self.state['pv_list'] = [1 if val in prevotes_list
                                     else 0 for val in self.addr_moniker_dict.values()]
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
        pc_percentage = 100*(pc_votes_in/total_voting_power)
        self.state['pc_list'] = [0 for i in range(len(self.addr_moniker_dict))]
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
                    except KeyError as kerr:
                        logging.exception(
                            f'PC> Validator address not found: {kerr}', exc_info=False)
            self.state['pc_list'] = [1 if val in precommits_list
                                     else 0 for val in self.addr_moniker_dict.values()]
            self.state['pc_percentage'] = f'{pc_percentage:.2f}%'
            self.state['pc_voting_power'] = f'{pc_votes_in}/{total_voting_power}'

    async def update_state(self) -> bool:
        """
        Update the state to be broadcast to websockets clients
        The state dictionary includes:
        - block height
        - vote stats for prevotes and precommits

        True is returned if the state changed from what it was previously,
        False is returned otherwise.
        """

        self.old_state = self.state
        self.state = {}
        version = self.get_version()
        if version:
            self.state['version'] = version
            if not self.node_online:
                logging.info('Node is online')
                self.node_online = True
        else:
            self.state['msg'] = 'Could not obtain version'
            if self.node_online:
                logging.info('Node is offline')
                self.node_online = False
            return self.state != self.old_state

        current_height = self.get_block_height()
        if current_height:
            self.state['height'] = current_height
            if not self.node_online:
                logging.info('Node is online')
                self.node_online = True
        else:
            self.state['msg'] = 'Could not obtain block height'
            if self.node_online:
                logging.info('Node is offline')
                self.node_online = False
            return self.state != self.old_state

        round_state = self.get_round_state()
        if round_state:
            await self.update_prevotes(round_state)
            await self.update_precommits(round_state)
            if not self.node_online:
                logging.info('Node is online')
                self.node_online = True
        else:
            self.state['msg'] = 'Could not obtain round state'
            if self.node_online:
                logging.info('Node is offline')
                self.node_online = False
            return self.state != self.old_state
        
        return self.state != self.old_state

    async def add_client(self, websocket):
        """
        Register websocket client, send current state
        """
        self.client_websockets.append(websocket)
        moniker_packet = {'monikers': list(self.addr_moniker_dict.values())}
        addr_packet = {'data_sources': self.node}
        try:
            await websocket.send(json.dumps(addr_packet))
            await websocket.send(json.dumps(moniker_packet))
            await websocket.send(json.dumps(self.state))
        except websockets.exceptions.ConnectionClosedError as cce:
            logging.exception(
                f'add_client> ConnectionClosedError: {cce}', exc_info=False)
        except websockets.exceptions.ConnectionClosedOK as cco:
            logging.exception(
                f'add_client> ConnectionClosedOK: {cco}', exc_info=False)
        except ConnectionResetError as cre:
            logging.exception(
                f'add_client> ConnectionResetError: {cre}', exc_info=False)
        except asyncio.exceptions.IncompleteReadError as ire:
            logging.exception(
                f'add_client> IncompleteReadError: {ire}', exc_info=False)

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
            if await self.update_state():
                state_json = json.dumps(self.state)
                results = await gather_limit(
                    MAX_CONCURRENT_SEND_COROS,
                    *[client.send(state_json) for client in self.client_websockets],
                    return_exceptions=True,
                )
                for result in results:
                    if isinstance(result, websockets.exceptions.ConnectionClosedError):
                        logging.exception(
                            f'monitor> ConnectionClosedError: {result}', exc_info=False)
                    if isinstance(result, websockets.exceptions.ConnectionClosedOK):
                        logging.exception(
                            f'monitor> ConnectionClosedOK: {result}', exc_info=False)
            
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
        logging.info('%s client(s) connected.', len(
            self.monitor.client_websockets))
        await websocket.wait_closed()
        await self.monitor.remove_client(websocket)
        logging.info('%s client(s) connected.', len(
            self.monitor.client_websockets))


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
                        default='1')
    parser.add_argument('-p', '--port',
                        help="the port to listen on for websockets connections",
                        nargs='?',
                        type=int,
                        default=9001)
    args = vars(parser.parse_args())
    # Configure Logging
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    ms = ConsensusMonitorServer(
        api_server=args['api'],
        rpc_server=args['rpc'],
        interval=args['interval'],
        port=args['port'])
    asyncio.run(ms.start_server())
