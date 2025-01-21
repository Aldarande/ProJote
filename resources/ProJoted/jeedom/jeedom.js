/* This file is part of Jeedom.
*
* Jeedom is free software: you can redistribute it and/or modify
* it under the terms of the GNU General Public License as published by
* the Free Software Foundation, either version 3 of the License, or
* (at your option) any later version.
*
* Jeedom is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
* GNU General Public License for more details.
*
* You should have received a copy of the GNU General Public License
* along with Jeedom. If not, see <http://www.gnu.org/licenses/>.
*/

const axios = require('axios');
var express = require('express');
<<<<<<< Updated upstream
=======
<<<<<<< HEAD
const http = require('http');

axios.defaults.httpAgent = new http.Agent({ keepAlive: false });
=======
>>>>>>> dev
>>>>>>> Stashed changes

var Jeedom = {}
Jeedom.log = {}
Jeedom.com = {}
Jeedom.http = {}

/***************************ARGS*******************************/

<<<<<<< Updated upstream
Jeedom.getArgs = function() {
=======
<<<<<<< HEAD
Jeedom.getArgs = function () {
>>>>>>> Stashed changes
  var result = {}
  var args = process.argv.slice(2,process.argv.length);
  for (var i = 0, len = args.length; i < len; i++) {
<<<<<<< Updated upstream
    if (args[i].slice(0,2) === '--') {
      result[args[i].slice(2,args[i].length)] = args[i + 1]
=======
    if (args[i].slice(0, 2) === '--') {
      result[args[i].slice(2, args[i].length)] = args[i + 1]
=======
Jeedom.getArgs = function() {
  var result = {}
  var args = process.argv.slice(2,process.argv.length);
  for (var i = 0, len = args.length; i < len; i++) {
    if (args[i].slice(0,2) === '--') {
      result[args[i].slice(2,args[i].length)] = args[i + 1]
>>>>>>> dev
>>>>>>> Stashed changes
    }
  }
  return result
}

/***************************LOGS*******************************/

<<<<<<< Updated upstream
Jeedom.log.setLevel = function(_level){
  var convert = {debug  : 0,info : 10,notice : 20,warning : 30,error : 40,critical : 50,none : 60}
=======
<<<<<<< HEAD
Jeedom.log.setLevel = function (_level) {
  var convert = { debug: 0, info: 10, notice: 20, warning: 30, error: 40, critical: 50, none: 60 }
>>>>>>> Stashed changes
  Jeedom.log.level = convert[_level]
}

Jeedom.log.debug  = function(_log){
  if(Jeedom.log.level > 0){
    return;
  }
  console.log('['+(new Date().toISOString().replace(/T/, ' ').replace(/\..+/, ''))+'][DEBUG] : '+_log)
}

Jeedom.log.info  = function(_log){
  if(Jeedom.log.level > 10){
    return;
  }
  console.log('['+(new Date().toISOString().replace(/T/, ' ').replace(/\..+/, ''))+'][INFO] : '+_log)
}

Jeedom.log.error  = function(_log){
  if(Jeedom.log.level > 40){
    return;
  }
<<<<<<< Updated upstream
  console.log('['+(new Date().toISOString().replace(/T/, ' ').replace(/\..+/, ''))+'][ERROR] : '+_log)
=======
  console.log('[' + (new Date().toISOString().replace(/T/, ' ').replace(/\..+/, '')) + '][ERROR] : ' + _log)
=======
Jeedom.log.setLevel = function(_level){
  var convert = {debug  : 0,info : 10,notice : 20,warning : 30,error : 40,critical : 50,none : 60}
  Jeedom.log.level = convert[_level]
}

Jeedom.log.debug  = function(_log){
  if(Jeedom.log.level > 0){
    return;
  }
  console.log('['+(new Date().toISOString().replace(/T/, ' ').replace(/\..+/, ''))+'][DEBUG] : '+_log)
}

Jeedom.log.info  = function(_log){
  if(Jeedom.log.level > 10){
    return;
  }
  console.log('['+(new Date().toISOString().replace(/T/, ' ').replace(/\..+/, ''))+'][INFO] : '+_log)
}

Jeedom.log.error  = function(_log){
  if(Jeedom.log.level > 40){
    return;
  }
  console.log('['+(new Date().toISOString().replace(/T/, ' ').replace(/\..+/, ''))+'][ERROR] : '+_log)
>>>>>>> dev
>>>>>>> Stashed changes
}

/***************************PID*******************************/

<<<<<<< Updated upstream
Jeedom.write_pid = function(_file){
  var fs = require('fs');
  fs.writeFile(_file, process.pid.toString(), function(err) {
    if(err) {
      Jeedom.log.error("Can't write pid file : "+err);
=======
<<<<<<< HEAD
Jeedom.write_pid = function (_file) {
  var fs = require('fs');
  fs.writeFile(_file, process.pid.toString(), function (err) {
    if (err) {
      Jeedom.log.error("Can't write pid file : " + err);
=======
Jeedom.write_pid = function(_file){
  var fs = require('fs');
  fs.writeFile(_file, process.pid.toString(), function(err) {
    if(err) {
      Jeedom.log.error("Can't write pid file : "+err);
>>>>>>> dev
>>>>>>> Stashed changes
      process.exit()
    }
  });
}

/***************************COM*******************************/

<<<<<<< Updated upstream
Jeedom.isObject = function(item) {
  return (item && typeof item === 'object' && !Array.isArray(item));
}

Jeedom.mergeDeep = function(target, ...sources) {
=======
<<<<<<< HEAD
Jeedom.isObject = function (item) {
  return (item && typeof item === 'object' && !Array.isArray(item));
}

Jeedom.mergeDeep = function (target, ...sources) {
=======
Jeedom.isObject = function(item) {
  return (item && typeof item === 'object' && !Array.isArray(item));
}

Jeedom.mergeDeep = function(target, ...sources) {
>>>>>>> dev
>>>>>>> Stashed changes
  if (!sources.length) return target;
  const source = sources.shift();
  if (Jeedom.isObject(target) && Jeedom.isObject(source)) {
    for (const key in source) {
      if (Jeedom.isObject(source[key])) {
        if (!target[key]) Object.assign(target, { [key]: {} });
        Jeedom.mergeDeep(target[key], source[key]);
      } else {
        Object.assign(target, { [key]: source[key] });
      }
    }
  }
  return Jeedom.mergeDeep(target, ...sources);
}

<<<<<<< Updated upstream
Jeedom.com.config = function(_apikey,_callback,_cycle){
=======
<<<<<<< HEAD
Jeedom.com.config = function (_apikey, _callback, _cycle) {
=======
Jeedom.com.config = function(_apikey,_callback,_cycle){
>>>>>>> dev
>>>>>>> Stashed changes
  Jeedom.com.apikey = _apikey;
  Jeedom.com.callback = _callback;
  Jeedom.com.cycle = _cycle;
  Jeedom.com.changes = {};
<<<<<<< Updated upstream
  if(Jeedom.com.cycle > 0){
    setInterval(function() {
      if(Object.keys(Jeedom.com.changes).length > 0){
=======
<<<<<<< HEAD
  if (Jeedom.com.cycle > 0) {
    setInterval(function () {
      if (Object.keys(Jeedom.com.changes).length > 0) {
=======
  if(Jeedom.com.cycle > 0){
    setInterval(function() {
      if(Object.keys(Jeedom.com.changes).length > 0){
>>>>>>> dev
>>>>>>> Stashed changes
        Jeedom.com.send_change_immediate(Jeedom.com.changes);
        Jeedom.com.changes = {};
      }
    }, Jeedom.com.cycle * 1000);
  }
}

<<<<<<< Updated upstream
Jeedom.com.add_changes = function(_key,_value){
  if (_key.indexOf('::') != -1){
    tmp_changes = {}
    var changes = _value
    var keys = _key.split('::').reverse();
    for (var k in keys){
      if (typeof tmp_changes[keys[k]] == 'undefined'){
=======
<<<<<<< HEAD
Jeedom.com.add_changes = function (_key, _value) {
  if (_key.indexOf('::') != -1) {
    tmp_changes = {}
    var changes = _value
    var keys = _key.split('::').reverse();
    for (var k in keys) {
      if (typeof tmp_changes[keys[k]] == 'undefined') {
=======
Jeedom.com.add_changes = function(_key,_value){
  if (_key.indexOf('::') != -1){
    tmp_changes = {}
    var changes = _value
    var keys = _key.split('::').reverse();
    for (var k in keys){
      if (typeof tmp_changes[keys[k]] == 'undefined'){
>>>>>>> dev
>>>>>>> Stashed changes
        tmp_changes[keys[k]] = {}
      }
      tmp_changes[keys[k]] = changes
      changes = tmp_changes
      tmp_changes = {}
    }
<<<<<<< Updated upstream
    if (Jeedom.com.cycle <= 0){
=======
<<<<<<< HEAD
    if (Jeedom.com.cycle <= 0) {
>>>>>>> Stashed changes
      Jeedom.com.send_change_immediate(changes)
    }else{
      Jeedom.com.changes = Jeedom.mergeDeep(Jeedom.com.changes,changes)
    }
<<<<<<< Updated upstream
=======
  } else {
    if (Jeedom.com.cycle <= 0) {
      Jeedom.com.send_change_immediate({ _key: _value })
    } else {
=======
    if (Jeedom.com.cycle <= 0){
      Jeedom.com.send_change_immediate(changes)
    }else{
      Jeedom.com.changes = Jeedom.mergeDeep(Jeedom.com.changes,changes)
    }
>>>>>>> Stashed changes
  } else{
    if (Jeedom.com.cycle <= 0){
      Jeedom.com.send_change_immediate({_key:_value})
    }else{
<<<<<<< Updated upstream
=======
>>>>>>> dev
>>>>>>> Stashed changes
      Jeedom.com.changes[_key] = _value
    }
  }
}

<<<<<<< Updated upstream
Jeedom.com.send_change_immediate = function(_changes){
  Jeedom.log.debug('Send data to jeedom : '+JSON.stringify(_changes));
=======
<<<<<<< HEAD
Jeedom.com.send_change_immediate = function (_changes) {
  Jeedom.log.debug('Send data to jeedom : ' + JSON.stringify(_changes));
>>>>>>> Stashed changes
  axios({
    method : 'POST',
    url:Jeedom.com.callback+'?apikey='+Jeedom.com.apikey,
    data: JSON.stringify(_changes)
  }).catch(function (error) {
      Jeedom.log.error('Error on send to jeedom : '+JSON.stringify(error));
  })
}

Jeedom.com.test = function(){
  axios({
    method:'GET',
    url:Jeedom.com.callback+'?apikey='+Jeedom.com.apikey
  }).catch(function (error) {
<<<<<<< Updated upstream
    Jeedom.log.error('Callback error.Please check your network configuration page : '+JSON.stringify(error));
=======
    Jeedom.log.error('Callback error.Please check your network configuration page : ' + JSON.stringify(error));
=======
Jeedom.com.send_change_immediate = function(_changes){
  Jeedom.log.debug('Send data to jeedom : '+JSON.stringify(_changes));
  axios({
    method : 'POST',
    url:Jeedom.com.callback+'?apikey='+Jeedom.com.apikey,
    data: JSON.stringify(_changes)
  }).catch(function (error) {
      Jeedom.log.error('Error on send to jeedom : '+JSON.stringify(error));
  })
}

Jeedom.com.test = function(){
  axios({
    method:'GET',
    url:Jeedom.com.callback+'?apikey='+Jeedom.com.apikey
  }).catch(function (error) {
    Jeedom.log.error('Callback error.Please check your network configuration page : '+JSON.stringify(error));
>>>>>>> dev
>>>>>>> Stashed changes
    process.exit();
  })
}

/***************************HTTP SERVER*******************************/

<<<<<<< Updated upstream
Jeedom.http.config = function(_port,_apikey){
=======
<<<<<<< HEAD
Jeedom.http.config = function (_port, _apikey) {
>>>>>>> Stashed changes
  Jeedom.http.apikey = _apikey;
  Jeedom.http.app = express();
  Jeedom.http.app.use(express.urlencoded({limit: '5mb'}));
  Jeedom.http.app.use(express.json({limit: '5mb'}));
  Jeedom.http.app.get('/', function(req, res) {
    res.setHeader('Content-Type', 'text/plain');
    res.status(404).send('Not found');
  });
  Jeedom.http.app.listen(_port,'127.0.0.1', function() {
    Jeedom.log.debug('HTTP listen on 127.0.0.1 port : '+_port+' started');
  });
}

<<<<<<< Updated upstream
Jeedom.http.checkApikey = function(_req){
=======
Jeedom.http.checkApikey = function (_req) {
=======
Jeedom.http.config = function(_port,_apikey){
  Jeedom.http.apikey = _apikey;
  Jeedom.http.app = express();
  Jeedom.http.app.use(express.urlencoded({limit: '5mb'}));
  Jeedom.http.app.use(express.json({limit: '5mb'}));
  Jeedom.http.app.get('/', function(req, res) {
    res.setHeader('Content-Type', 'text/plain');
    res.status(404).send('Not found');
  });
  Jeedom.http.app.listen(_port,'127.0.0.1', function() {
    Jeedom.log.debug('HTTP listen on 127.0.0.1 port : '+_port+' started');
  });
}

Jeedom.http.checkApikey = function(_req){
>>>>>>> dev
>>>>>>> Stashed changes
  return (_req.query.apikey === Jeedom.http.apikey)
}

/***************************EXPORTS*******************************/

exports.getArgs = Jeedom.getArgs;
exports.log = Jeedom.log;
exports.write_pid = Jeedom.write_pid;
exports.com = Jeedom.com;
<<<<<<< Updated upstream
exports.http = Jeedom.http;
=======
<<<<<<< HEAD
exports.http = Jeedom.http;
=======
exports.http = Jeedom.http;
>>>>>>> dev
>>>>>>> Stashed changes
