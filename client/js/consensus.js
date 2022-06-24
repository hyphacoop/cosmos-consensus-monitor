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

wso.onmessage = async function (event) {
    let data = JSON.parse(await event.data);
    // console.log("ws:", data);

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
    if (data.hasOwnProperty('pv_list')) {
        let prevote_list = data['pv_list'];
        while (prevotes_validators.firstChild) {
            prevotes_validators.removeChild(prevotes_validators.firstChild);
        };
        prevote_list.forEach(prevote => {
            let validator = document.createElement('div');
            validator.setAttribute('class', 'vote monitored-field');
            validator.textContent = prevote
            prevotes_validators.appendChild(validator)
        });
    };
    if (data.hasOwnProperty('pc_percentage')) {
        let pc_percentage = data['pc_percentage'];
        precommits_ratio_div.textContent = pc_percentage;
    };
    if (data.hasOwnProperty('pc_voting_power')) {
        let pc_voting_power = data['pc_voting_power'];
        precommits_vp_div.textContent = pc_voting_power;
    };
    if (data.hasOwnProperty('pc_list')) {
        let precommit_list = data['pc_list'];
        while (precommits_validators.firstChild) {
            precommits_validators.removeChild(precommits_validators.firstChild);
        };
        precommit_list.forEach(precommit => {
            let validator = document.createElement('div');
            validator.setAttribute('class', 'vote monitored-field');
            validator.textContent = precommit
            precommits_validators.appendChild(validator)
        });
    };

};
