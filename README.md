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

## Using the Monitor

### Websockets Server

The syntax for the websockets server is as follows:

```
server/consensus_monitor_server.py --api <api_server_node> --rpc <rpc_server_node> --port <websockets_port>
```

- `api_server_node` and `rpc_server_node` are required
- `port` is set to 9001 by default

#### Service

You can run the websockets server as a service:

1. Modify the `monitor-ws-server.service` file with adequate user name, path, and RPC/API node entries.
2. Make a copy of `monitor-ws-server.service` or create a link to it in `/etc/systemd/system/`.
3. Enable and start the service:
```
systemctl daemon-reload
systemctl enable monitor-ws-server.service
systemctl start monitor-ws-server.service
systemctl status monitor-ws-server.service
```

### Web Client

You can serve the web client using the `http` package:

```
python -m http.server --directory client/
```

- `consensus.js` uses port 9001 to connect to the Websockets server by default.


#### Service

You can run the http server as a service:

1. Modify the `monitor-ui-server.service` file with adequate user name, path, and port entries.
2. Make a copy of `monitor-ui-server.service` or create a link to it in `/etc/systemd/system/`.
3. Enable and start the service:
```
systemctl daemon-reload
systemctl enable monitor-ui-server.service
systemctl start monitor-ui-server.service
systemctl status monitor-ui-server.service
