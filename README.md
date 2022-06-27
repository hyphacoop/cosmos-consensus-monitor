# Cosmos Consensus Monitor

A real-time monitoring tool for the Cosmos consensus status.

The monitor is made up of two parts:

- A websockets server that queries a Cosmos node continuously.
- A web client that opens a websockets connection to the server.

## Setup

- Requires Python 3.10

1. Clone repo: `git clone git@github.com:hyphacoop/cosmos-consensus-monitor.git`
2. Change directory: `cd cosmos-consensus-monitor`
3. Create a python virtual environment: `python -m venv .env`
4. Source env shell vars: `source .env/bin/activate`
5. Install requirements: `pip install -r requirements.txt`

## Usage

### Websockets server

The syntax for the websockets server is as follows:

```
server/consensus_monitor_server.py --api <api_server_node> --rpc <rpc_server_node> --port <websockets_port> --interval <polling_interval>
```

- `api_server_node` and `rpc_server_node` are required
- `port` is set to 9001 by default
- `interval` is set to 1 by default

### Web client

You can serve the web client using the `http` package:

```
python -m http.server --directory client/
```

