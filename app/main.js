// Copyright 2013 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
// This code has been adapted to support integration of Chrome as a PDF
// viewer for the CB-FLTS.

var port = null;

// Response types
var SUCCESS = 0;
var ERROR = 1;
var UNKNOWN = 2;

var getKeys = function(obj){
   var keys = [];
   for(var key in obj){
      keys.push(key);
   }
   return keys;
}

function updateUiState() {
  if (port) {
    document.getElementById('connect-button').style.display = 'none';
    document.getElementById('input-text').style.display = 'block';
    document.getElementById('send-message-button').style.display = 'block';
  } else {
    document.getElementById('connect-button').style.display = 'block';
    document.getElementById('input-text').style.display = 'none';
    document.getElementById('send-message-button').style.display = 'none';
  }
}

function onDisconnected() {
  appendMessage("Failed to connect: " + chrome.runtime.lastError.message);
  port = null;
  updateUiState();
}

function connect() {
  var hostName = "com.flts.chrome.bridge";
  appendMessage("Connecting to native messaging host <b>" + hostName + "</b>");
  port = chrome.runtime.connectNative(hostName);
  port.onMessage.addListener(onFLTSCommand);
  port.onDisconnect.addListener(onDisconnected);
  updateUiState();
}

function appendMessage(text) {
  document.getElementById('response').innerHTML += "<p>" + text + "</p>";
}

document.addEventListener('DOMContentLoaded', function () {
  document.getElementById('connect-button').addEventListener(
      'click', connect);
  updateUiState();
});

// Extract command type and corresponding data.
function onFLTSCommand(message){
  if (typeof message === 'string'){
    appendMessage(message);
  }

  // Do not handle any other type that is not an object
  if (typeof message !== 'object'){
    return;
  }

  // Check if it has the key properties required to process the request.
  var hasTypeProp = message.hasOwnProperty('type');
  var hasDataProp = message.hasOwnProperty('data');
  var hasRequestIdProp = message.hasOwnProperty('requestId');
  if (hasTypeProp && hasDataProp && hasRequestIdProp){
    appendMessage(JSON.stringify(message));
    parseCommand(message.type, message.data, message.requestId)
  }
}

// Execute appropriate function based on the command type
function parseCommand(messageType, data, requestId){
  switch(messageType){
    case 0:
      renameTab(data, requestId);
      break;

    case 1:
      closeTabs(data, requestId);
      break;

    default:
      sendFLTSResponse(
        ERROR,
        {"msg": "Request type could not be determined"},
        requestId
      );
      appendMessage('Request type could not be determined.');
  }
}

// Create and send command response
function sendFLTSResponse(responseType, data, requestId){
  var commResponse = {
    "type": responseType,
    "data": data,
    "source": 'chrome',
    "requestId": requestId
  };
  port.postMessage(commResponse);
  appendMessage("Sent message: <b>" + JSON.stringify(commResponse) + "</b>");
}

/* Renames a tab by searching for a match of the current name and
replacing it with new_name. */
function renameTab(data, requestId){
  var msg = 'Execution incomplete';
  var tabId = -1;
  var winId = -1;
  chrome.tabs.query({
	  title: data.current_name
	}, function(tabs){
	    if (tabs.length > 0){
	      tab = tabs[0];
	      tabId = tab.id;
	      winId = tab.windowId;
	      chrome.tabs.executeScript(
	        tab.id,
	        {code: "document.title = ".concat(
	        "'", data.new_name, "'"
	        )},
	        function(res){
              msg = "Tab title replaced";
              sendFLTSResponse(SUCCESS, {
                "msg": msg,
                "tabId": tabId,
                "windowId": winId
              }, requestId);
	        }
	      );
	    } else {
	        msg = "Tab not found";
	        sendFLTSResponse(ERROR, {"msg": msg}, requestId);
	    }
	}
  );
}

// Closes a tab given its id.
function closeTabs(data, requestId){
  getExistingTabIds(
    data.tabIds,
    function(validIds){
      if (validIds.length == 0){
        sendFLTSResponse(
            ERROR,
            {"msg": "No matching tabs to close"},
            requestId
        );
      } else {
        // Close the tabs with the givens ids
        chrome.tabs.remove(
          validIds,
          function(){
            sendFLTSResponse(SUCCESS, {"msg": 'Tabs closed'}, requestId);
          }
        );
      }
    }
  );
}

/* Returns an array of existing tab ids based on the input array. This is
useful when performing operations that require a valid tab id to be specified
otherwise an exception will be raised.
*/
function getExistingTabIds(tabIds, callback){
  chrome.windows.getAll(
    {populate: true},
    function(windows){
      allTabIds = [];
      for (var i = 0; i < windows.length; i++){
        for (var j = 0; j < windows[i].tabs.length; j++){
          allTabIds.push(windows[i].tabs[j].id);
        }
      }
      var validTabIds = [];
      // Loop through each tabId and validate against the param list.
      for (t = 0; t < tabIds.length; t++){
        if (allTabIds.indexOf(tabIds[t]) !== -1){
          validTabIds.push(tabIds[t]);
        }
      }
      if (typeof callback === "function"){
        callback(validTabIds);
      }
    }
  );
}
