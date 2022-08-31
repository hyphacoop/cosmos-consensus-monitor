let connection_status = document.getElementById("connection-status-container")
let version_div = document.getElementById("version");
let block_height_div = document.getElementById("block-height");
let prevotes_ratio_div = document.getElementById("prevotes-percentage");
let prevotes_validators = document.getElementById("prevotes-validators");
let precommits_ratio_div = document.getElementById("precommits-percentage");
let precommits_validators = document.getElementById("precommits-validators");
let pv_bar_box = document.getElementById('prevotes-bar-box');
let pc_bar_box = document.getElementById('precommits-bar-box');

var wsProto = "ws://";
if (window.location.protocol === "https:") {
    wsProto = "wss://";
}
var wso = new WebSocket(wsProto + document.domain + ":" + "9001" + "/");

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

function setProgress(box, progress) {
    // Add the relevant number of bars to the progress box
    while (box.firstChild) {
        box.removeChild(box.firstChild);
    }

    let vote_passed = ''
    if (progress >= 67) {
        vote_passed = '_pass';
    }

    for (let i = 0; i < progress; ++i) {
        bar = document.createElement('div');
        bar.className = 'progress_bar' + vote_passed;
        box.appendChild(bar)
    };

};

wso.onopen = function (evt) {
    connection_status.style.display = "none";
}

wso.onclose = function (evt) {
    connection_status.style.display = "block";
};

wso.onmessage = async function (event) {
    let data = JSON.parse(await event.data);
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
        let pv_percentage = parseInt(data['pv_percentage']);
        prevotes_ratio_div.textContent = pv_percentage + '%';
        setProgress(pv_bar_box, pv_percentage);
    };
    if (data.hasOwnProperty('pv_list') && data['pv_list'].length > 0) {
        let prevote_list = data['pv_list'];
        prevotes_validators.childNodes.forEach(val => {
            val.classList.remove('voted');
        });
        for (let i = 0; i < prevote_list.length; ++i) {
            if (prevote_list[i] == 1) {
                prevotes_validators.childNodes[i].classList.add('voted');
            }
        };
    };
    if (data.hasOwnProperty('pc_percentage')) {
        let pc_percentage = parseInt(data['pc_percentage']);
        precommits_ratio_div.textContent = pc_percentage + '%';
        setProgress(pc_bar_box, pc_percentage);
    };
    if (data.hasOwnProperty('pc_list') && data['pc_list'].length > 0) {
        let precommit_list = data['pc_list'];
        precommits_validators.childNodes.forEach(val => {
            val.classList.remove('voted');
        });
        for (let i = 0; i < precommit_list.length; ++i) {
            if (precommit_list[i]) {
                precommits_validators.childNodes[i].classList.add('voted');
            }
        };
    };
};

