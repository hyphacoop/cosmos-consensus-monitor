let api_div = document.getElementById("api-address");
let rpc_div = document.getElementById("rpc-address");
let version_div = document.getElementById("version-field");
let block_height_div = document.getElementById("block-height");
let prevotes_ratio_div = document.getElementById("prevotes-ratio");
let prevotes_vp_div = document.getElementById("prevotes-voting-power");
let prevotes_validators = document.getElementById("prevotes-validators");
let precommits_ratio_div = document.getElementById("precommits-ratio");
let precommits_vp_div = document.getElementById("precommits-voting-power");
let precommits_validators = document.getElementById("precommits-validators");

var wso = new WebSocket("ws://" + document.domain + ":" + "9001" + "/");
wso.onopen = function (evt) {
    console.log("WS Connected");
}
wso.onclose = function (evt) {
    console.log("WS not Connected")
};

function populate_validators(monikers) {
    while (prevotes_validators.firstChild) {
        prevotes_validators.removeChild(prevotes_validators.firstChild);
    };
    while (precommits_validators.firstChild) {
        precommits_validators.removeChild(precommits_validators.firstChild);
    };
    monikers.forEach(moniker => {
        let validator_pv = document.createElement("div");
        validator_pv.setAttribute("class", "vote");
        validator_pv.textContent = moniker;
        prevotes_validators.appendChild(validator_pv);
        let validator_pc = document.createElement("div");
        validator_pc.setAttribute("class", "vote");
        validator_pc.textContent = moniker;
        precommits_validators.appendChild(validator_pc);
    });
}

wso.onmessage = async function (event) {
    let data = JSON.parse(await event.data);

    if (data.hasOwnProperty('data_sources')) {
        api_div.textContent = data['data_sources']['api'];
        rpc_div.textContent = data['data_sources']['rpc'];
    };
    if (data.hasOwnProperty('monikers')) {
        populate_validators(data['monikers']);
    };
    if (data.hasOwnProperty('version')) {
        let version = data['version'];
        version_div.textContent = version;
    };
    if (data.hasOwnProperty('height')) {
        let block_height = data['height'];
        block_height_div.textContent = block_height;
    };
    if (data.hasOwnProperty('pv_percentage')) {
        let pv_percentage = data['pv_percentage'];
        prevotes_ratio_div.textContent = pv_percentage;
    };
    if (data.hasOwnProperty('pv_voting_power')) {
        let pv_voting_power = data['pv_voting_power'];
        prevotes_vp_div.textContent = pv_voting_power;
    };
    if (data.hasOwnProperty('pv_list') && data['pv_list'].length > 0) {
        let prevote_list = data['pv_list'];
        prevotes_validators.childNodes.forEach(val => {
            val.classList.remove('voted');
        });
        for (let i=0; i<prevote_list.length; ++i) {
            if (prevote_list[i] == 1) {
                prevotes_validators.childNodes[i].classList.add('voted');
            }
        };
    };
    if (data.hasOwnProperty('pc_percentage')) {
        let pc_percentage = data['pc_percentage'];
        precommits_ratio_div.textContent = pc_percentage;
    };
    if (data.hasOwnProperty('pc_voting_power')) {
        let pc_voting_power = data['pc_voting_power'];
        precommits_vp_div.textContent = pc_voting_power;
    };
    if (data.hasOwnProperty('pc_list') && data['pc_list'].length > 0) {
        let precommit_list = data['pc_list'];
        precommits_validators.childNodes.forEach(val => {
            val.classList.remove('voted');
        });
        for (let i=0; i<precommit_list.length; ++i) {
            if (precommit_list[i]) {
                precommits_validators.childNodes[i].classList.add('voted');
            }
        };
    };

};
