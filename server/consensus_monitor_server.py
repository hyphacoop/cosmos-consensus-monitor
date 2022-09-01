#!/usr/bin/env python
"""
A websockets server that provides real-time data on the consensus process of a Cosmos chain:
- During initialization,
-  1. the active validator set is recorded using API and RPC queries
-  2. subscriptions are created for Vote, NewRoundStep, and ValidatorSetUpdates events
- As soon as an event is received, the consensus state is queried
  to obtain the prevotes and precommits as a percentage of the total voting power.

Syntax:
./consensus_monitor_server.py -a <API server> -r <RPC server> -p <ws listening port>
Example:
./consensus_monitor_server.py -a api.cosmos.network -r rpc.cosmos.network -p 9090

"""
import urllib.parse
import json
import argparse
import logging
import sys
import asyncio
import requests
import websockets


async def gather_limit(max_coros, *awaits, return_exceptions=False):
    """
    Like asyncio.gather but concurrency is limited to 'max_coros' at a time.

    Source: https://stackoverflow.com/a/61478547
    """

    semaphore = asyncio.Semaphore(max_coros)

    async def sem_aw(coro):
        async with semaphore:
            return await coro
    return await asyncio.gather(*(sem_aw(aw) for aw in awaits), return_exceptions=return_exceptions)


class ConsensusMonitor:
    """
    Requests and parses consensus data from a Cosmos node.
    Packages the data and forwards it to all connected websockets clients.
    """
    API_ENDPOINT_VALIDATORS = '/cosmos/staking/v1beta1/validators'
    RPC_ENDPOINT_VALIDATORS = '/validators'
    RPC_ENDPOINT_ABCI_INFO = '/abci_info'
    RPC_ENDPOINT_BLOCK = '/block'
    RPC_ENDPOINT_CONSENSUS = '/consensus_state'
    WS_EVENT_SUBSCRIPTIONS = [
        '{ "jsonrpc": "2.0", "method": "subscribe", \
            "params": ["tm.event=\'Vote\'"], "id": 1 }',
        '{ "jsonrpc": "2.0", "method": "subscribe", \
            "params": ["tm.event=\'NewRoundStep\'"], "id": 2 }',
        '{ "jsonrpc": "2.0", "method": "subscribe", \
            "params": ["tm.event=\'ValidatorSetUpdates\'"], "id": 3 }'
    ]
    # The maximum number of websocket .send coroutines running at once
    # Larger number means more concurrent bandwidth usage,
    # also probably a bit more CPU usage?
    MAX_CONCURRENT_SEND_COROS = 100

    def __init__(self,
                 api_server: str,
                 rpc_server: str):
        self.node = {'api': api_server,
                     'rpc': rpc_server}
        self.node_online = False
        self.state = {'prevote_addresses': [],
                      'precommit_addresses': [],
                      'round_step': 'RoundStepPropose'}
        self.old_state = {}
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

    def get_round_state(self):
        """
        Obtain the current round state through the RPC server
        """
        try:
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
        ratio = pv_bit_array.split()[1]
        pv_votes_in = int(ratio.split("/")[0])
        total_voting_power = int(ratio.split("/")[1])
        pv_percentage = 100*(pv_votes_in/total_voting_power)
        self.state['pv_list'] = [0 for i in range(len(self.addr_moniker_dict))]
        self.state['pv_percentage'] = '0.00%'
        self.state['prevote_addresses'] = []

        # if pv_validators_voted > 0:
        if pv_votes_in > 0:
            prevotes_list = []
            for prevote in prevotes:
                if prevote != 'nil-Vote':
                    # consensus address is clipped to 12 characters
                    addr = prevote.split(':')[1].split(' ')[0]
                    self.state['prevote_addresses'].append(addr)
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
        ratio = pc_bit_array.split()[1]
        pc_votes_in = int(ratio.split("/")[0])
        total_voting_power = int(ratio.split("/")[1])
        pc_percentage = 100*(pc_votes_in/total_voting_power)
        self.state['pc_list'] = [0 for i in range(len(self.addr_moniker_dict))]
        self.state['pc_percentage'] = '0.00%'
        self.state['prevote_addresses'] = []

        if pc_votes_in > 0:
            precommits_list = []
            for precommit in precommits:
                if precommit != 'nil-Vote':
                    # consensus address is clipped to 12 characters
                    addr = precommit.split(':')[1].split(' ')[0]
                    self.state['prevote_addresses'].append(addr)
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

    async def update_state(self):
        """
        Update the prevotes and precommits, broadcast state to websockets clients
        The state dictionary includes:
        - prevote validators and % of voting power
        - precommit validators and % of voting power
        - current round step
        """
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
        await self.broadcast(json.dumps(self.state))

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

    async def process_query_response(self, data):
        """
        Parse subscription event data
        Handles Vote, NewRoundStep and ValidatorSetUpdates events
        """
        value = data['data']['value']
        new_event = data['query'].split('=')[1].split("'")[1]
        if new_event == 'Vote':
            if self.state['round_step'] == 'RoundStepPrevote':
                if (value['Vote']['type'] == 1) and \
                        (value['Vote']['validator_address'][:12] in self.addr_moniker_dict):
                    await self.update_state()
            elif self.state['round_step'] == 'RoundStepPrecommit':
                if (value['Vote']['type'] == 2) and \
                        (value['Vote']['validator_address'][:12] in self.addr_moniker_dict):
                    await self.update_state()
        elif new_event == 'NewRoundStep':
            self.state['round_step'] = value['step']
            await self.update_state()
            if self.state['round_step'] == 'RoundStepNewHeight':
                msg = json.dumps({'height': value['height']})
                await self.broadcast(msg)
                msg = json.dumps({'version': self.get_version()})
                await self.broadcast(msg)
        elif new_event == 'ValidatorSetUpdates':
            logging.info('Validator set has been updated')
            self.generate_addr_moniker_dict()
            moniker_packet = {'monikers': list(
                self.addr_moniker_dict.values())}
            await self.broadcast(json.dumps(moniker_packet))
            await self.update_state()

    async def subscribe(self):
        """
        Subscribes to Tendermint RPC websocket endpoints
        """
        ws_url = self.node['rpc'].replace('http', 'ws')
        ws_url = ws_url.replace('https', 'wss')
        ws_url = ws_url + '/websocket'
        async for websocket in websockets.connect(ws_url):
            try:
                for sub in self.WS_EVENT_SUBSCRIPTIONS:
                    await websocket.send(sub)
                    await websocket.recv()
                while True:
                    data = json.loads(await websocket.recv())['result']
                    if 'query' in data:
                        await self.process_query_response(data)
            except websockets.exceptions.ConnectionClosedError as cce:
                print("subscription> Connection Closed Error: ", cce)

    async def broadcast(self, message):
        """
        Sends the message to all connected websocket clients
        """
        results = await gather_limit(
            self.MAX_CONCURRENT_SEND_COROS,
            *[client.send(message)
              for client in self.client_websockets],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, websockets.exceptions.ConnectionClosedError):
                logging.exception(
                    f'monitor> ConnectionClosedError: {result}', exc_info=False)
            if isinstance(result, websockets.exceptions.ConnectionClosedOK):
                logging.exception(
                    f'monitor> ConnectionClosedOK: {result}', exc_info=False)


class ConsensusMonitorServer:
    """
    Websockets server for monitoring the Cosmos consensus state
    Must specify:
    - API server (including port)
    - RPC server (including port)
    - Port for incoming websockets connections
    """

    def __init__(self, api_server: str, rpc_server, port: int):
        self.port = port
        self.monitor = ConsensusMonitor(
            api_server=api_server, rpc_server=rpc_server)

    async def start_server(self):
        """
        Start listening for websockets connections and consensus monitoring
        """
        async with websockets.serve(self.handler, "", self.port):
            await self.monitor.subscribe()
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
        port=args['port'])

    asyncio.run(ms.start_server())
