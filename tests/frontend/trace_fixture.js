/*
 * LIBI for Home Assistant - Copyright (C) 2026 Guy Azria - GPL-3.0-or-later
 * [ADDED v1.0.0 | 2026-11-06] Purpose: Real runs of a real Home Assistant (pytest-homeassistant-custom-component, HA of
 *   requirements_test.txt), captured on 2026-11-06 for the Online tests: three automations - Garden (two triggers with
 *   ids and one choose: valve on, a delay of 3 s, valve off; stop), Porch (a trigger with a for of 3 s), Bell (an
 *   action Home Assistant does not have) - their NETs as LIBI's importer drew them (src: where each block is in the
 *   YAML), and at each moment the states, the time, and the newest run of each automation as trace/list and trace/get
 *   answered (trimmed to what Online reads). Not a test page: the runner runs test_*.html only.
 */
export const CAPTURE = {
 "nets": [
  {
   "id": "n1",
   "ha_id": "garden",
   "name": "Garden",
   "description": "",
   "collapsed": false,
   "level": "automation",
   "mode": "single",
   "max": null,
   "variables": null,
   "extra": {},
   "rungs": [
    {
     "id": "r1",
     "comment": "When go turns on, if enabled is on, then turn on valve and wait 00:00:03 and turn off valve",
     "elements": [
      {
       "id": "e3",
       "type": "contact_no",
       "isTrigger": true,
       "label": "input_boolean.go",
       "src": "actions[0].opt[0].cond[0]",
       "trigId": "start",
       "sig": "type=contact_no|label=input_boolean.go|sourceA=|sourceB=|sourceC=|target=|source=|mode=|title=|tts=|stream=|value=|valueKey=|loopType=|weekdays=|precision=|fallback=|kind="
      },
      {
       "id": "e4",
       "type": "contact_no",
       "isTrigger": false,
       "label": "input_boolean.enabled",
       "src": "actions[0].opt[0].cond[1]",
       "sig": "type=contact_no|label=input_boolean.enabled|sourceA=|sourceB=|sourceC=|target=|source=|mode=|title=|tts=|stream=|value=|valueKey=|loopType=|weekdays=|precision=|fallback=|kind="
      },
      {
       "id": "e5",
       "type": "coil_s",
       "isTrigger": false,
       "label": "input_boolean.valve",
       "service": "input_boolean.turn_on",
       "src": "actions[0].opt[0].seq[0]",
       "targetSpec": {
        "entity_id": [
         "input_boolean.valve"
        ]
       },
       "fromAction": true,
       "sig": "type=coil_s|label=input_boolean.valve|sourceA=|sourceB=|sourceC=|target=|source=|mode=|title=|tts=|stream=|value=|valueKey=|loopType=|weekdays=|precision=|fallback=|kind="
      },
      {
       "id": "e6",
       "type": "timer_ton",
       "isTrigger": false,
       "label": "00:00:03",
       "src": "actions[0].opt[0].seq[1]",
       "fromAction": true,
       "sig": "type=timer_ton|label=00:00:03|sourceA=|sourceB=|sourceC=|target=|source=|mode=|title=|tts=|stream=|value=|valueKey=|loopType=|weekdays=|precision=|fallback=|kind="
      },
      {
       "id": "e7",
       "type": "coil_r",
       "isTrigger": false,
       "label": "input_boolean.valve",
       "service": "input_boolean.turn_off",
       "src": "actions[0].opt[0].seq[2]",
       "targetSpec": {
        "entity_id": [
         "input_boolean.valve"
        ]
       },
       "fromAction": true,
       "sig": "type=coil_r|label=input_boolean.valve|sourceA=|sourceB=|sourceC=|target=|source=|mode=|title=|tts=|stream=|value=|valueKey=|loopType=|weekdays=|precision=|fallback=|kind="
      }
     ],
     "group": "g1",
     "groupIdx": 0,
     "groupTotal": 2,
     "groupKind": "choose",
     "isDefault": false,
     "src": "actions[0]"
    },
    {
     "id": "r2",
     "comment": "When stop turns on, then turn off valve",
     "elements": [
      {
       "id": "e8",
       "type": "contact_no",
       "isTrigger": true,
       "label": "input_boolean.stop",
       "src": "actions[0].opt[1].cond[0]",
       "trigId": "stop",
       "sig": "type=contact_no|label=input_boolean.stop|sourceA=|sourceB=|sourceC=|target=|source=|mode=|title=|tts=|stream=|value=|valueKey=|loopType=|weekdays=|precision=|fallback=|kind="
      },
      {
       "id": "e9",
       "type": "coil_r",
       "isTrigger": false,
       "label": "input_boolean.valve",
       "service": "input_boolean.turn_off",
       "src": "actions[0].opt[1].seq[0]",
       "targetSpec": {
        "entity_id": [
         "input_boolean.valve"
        ]
       },
       "fromAction": true,
       "sig": "type=coil_r|label=input_boolean.valve|sourceA=|sourceB=|sourceC=|target=|source=|mode=|title=|tts=|stream=|value=|valueKey=|loopType=|weekdays=|precision=|fallback=|kind="
      }
     ],
     "group": "g1",
     "groupIdx": 1,
     "groupTotal": 2,
     "groupKind": "choose",
     "isDefault": false,
     "src": "actions[0]"
    }
   ],
   "links": [],
   "source": "ha"
  },
  {
   "id": "n2",
   "ha_id": "porch",
   "name": "Porch",
   "description": "",
   "collapsed": false,
   "level": "automation",
   "mode": "single",
   "max": null,
   "variables": null,
   "extra": {},
   "rungs": [
    {
     "id": "r1",
     "comment": "When door turns on for 00:00:03, then turn on lamp",
     "elements": [
      {
       "id": "e4",
       "type": "contact_no",
       "isTrigger": true,
       "label": "input_boolean.door",
       "src": "triggers[0]",
       "forTimer": true,
       "autoGate": true,
       "sig": "type=contact_no|label=input_boolean.door|sourceA=|sourceB=|sourceC=|target=|source=|mode=|title=|tts=|stream=|value=|valueKey=|loopType=|weekdays=|precision=|fallback=|kind="
      },
      {
       "id": "e5",
       "type": "timer_ton",
       "isTrigger": false,
       "label": "00:00:03",
       "src": "triggers[0]",
       "isFor": true,
       "forValue": {
        "seconds": 3
       },
       "autoGate": true
      },
      {
       "id": "e2",
       "type": "coil_s",
       "isTrigger": false,
       "label": "input_boolean.lamp",
       "service": "input_boolean.turn_on",
       "src": "actions[0]",
       "targetSpec": {
        "entity_id": [
         "input_boolean.lamp"
        ]
       },
       "fromAction": true,
       "sig": "type=coil_s|label=input_boolean.lamp|sourceA=|sourceB=|sourceC=|target=|source=|mode=|title=|tts=|stream=|value=|valueKey=|loopType=|weekdays=|precision=|fallback=|kind="
      }
     ]
    }
   ],
   "links": [],
   "source": "ha"
  },
  {
   "id": "n3",
   "ha_id": "bell",
   "name": "Bell",
   "description": "",
   "collapsed": false,
   "level": "automation",
   "mode": "single",
   "max": null,
   "variables": null,
   "extra": {},
   "rungs": [
    {
     "id": "r1",
     "comment": "When bell turns on, then send a notification to does not exist",
     "elements": [
      {
       "id": "e3",
       "type": "contact_no",
       "isTrigger": true,
       "label": "input_boolean.bell",
       "src": "triggers[0]",
       "autoGate": true,
       "sig": "type=contact_no|label=input_boolean.bell|sourceA=|sourceB=|sourceC=|target=|source=|mode=|title=|tts=|stream=|value=|valueKey=|loopType=|weekdays=|precision=|fallback=|kind="
      },
      {
       "id": "e2",
       "type": "move",
       "isTrigger": false,
       "mode": "notify",
       "target": "notify.does_not_exist",
       "source": "ding",
       "title": "",
       "tts": "",
       "stream": "",
       "src": "actions[0]",
       "fromAction": true,
       "sig": "type=move|label=|sourceA=|sourceB=|sourceC=|target=notify.does_not_exist|source=ding|mode=notify|title=|tts=|stream=|value=|valueKey=|loopType=|weekdays=|precision=|fallback=|kind="
      }
     ]
    }
   ],
   "links": [],
   "source": "ha"
  }
 ],
 "moments": [
  {
   "name": "garden running: the valve is on, the delay is counting",
   "now": "2026-11-06T18:55:52.759998+00:00",
   "states": {
    "input_boolean.go": {
     "entity_id": "input_boolean.go",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.539163+00:00",
     "last_updated": "2026-11-06T18:55:51.539163+00:00",
     "attributes": {
      "friendly_name": "Go"
     }
    },
    "input_boolean.stop": {
     "entity_id": "input_boolean.stop",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.349550+00:00",
     "last_updated": "2026-11-06T18:55:51.349550+00:00",
     "attributes": {
      "friendly_name": "Stop"
     }
    },
    "input_boolean.enabled": {
     "entity_id": "input_boolean.enabled",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.537912+00:00",
     "last_updated": "2026-11-06T18:55:51.537912+00:00",
     "attributes": {
      "friendly_name": "Enabled"
     }
    },
    "input_boolean.valve": {
     "entity_id": "input_boolean.valve",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.547102+00:00",
     "last_updated": "2026-11-06T18:55:51.547102+00:00",
     "attributes": {
      "friendly_name": "Valve"
     }
    },
    "input_boolean.door": {
     "entity_id": "input_boolean.door",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.350570+00:00",
     "last_updated": "2026-11-06T18:55:51.350570+00:00",
     "attributes": {
      "friendly_name": "Door"
     }
    },
    "input_boolean.lamp": {
     "entity_id": "input_boolean.lamp",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.350861+00:00",
     "last_updated": "2026-11-06T18:55:51.350861+00:00",
     "attributes": {
      "friendly_name": "Lamp"
     }
    },
    "input_boolean.bell": {
     "entity_id": "input_boolean.bell",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.351105+00:00",
     "last_updated": "2026-11-06T18:55:51.351105+00:00",
     "attributes": {
      "friendly_name": "Bell"
     }
    },
    "automation.garden": {
     "entity_id": "automation.garden",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.404506+00:00",
     "last_updated": "2026-11-06T18:55:51.541209+00:00",
     "attributes": {
      "id": "garden",
      "last_triggered": "2026-11-06T18:55:51.541172+00:00",
      "mode": "single",
      "current": 1,
      "friendly_name": "Garden"
     }
    },
    "automation.porch": {
     "entity_id": "automation.porch",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.406793+00:00",
     "last_updated": "2026-11-06T18:55:51.406793+00:00",
     "attributes": {
      "id": "porch",
      "last_triggered": null,
      "mode": "single",
      "current": 0,
      "friendly_name": "Porch"
     }
    },
    "automation.bell": {
     "entity_id": "automation.bell",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.408589+00:00",
     "last_updated": "2026-11-06T18:55:51.408589+00:00",
     "attributes": {
      "id": "bell",
      "last_triggered": null,
      "mode": "single",
      "current": 0,
      "friendly_name": "Bell"
     }
    }
   },
   "runs": {
    "garden": {
     "list": {
      "last_step": "action/0/choose/0/sequence/1",
      "run_id": "77c9d60905aec1a002036786140493d7",
      "state": "running",
      "script_execution": null,
      "timestamp": {
       "start": "2026-11-06T18:55:51.540161+00:00",
       "finish": null
      },
      "domain": "automation",
      "item_id": "garden",
      "trigger": "state of input_boolean.go"
     },
     "get": {
      "run_id": "77c9d60905aec1a002036786140493d7",
      "state": "running",
      "script_execution": null,
      "last_step": "action/0/choose/0/sequence/1",
      "error": null,
      "timestamp": {
       "start": "2026-11-06T18:55:51.540161+00:00",
       "finish": null
      },
      "trigger": "state of input_boolean.go",
      "config": {
       "id": "garden",
       "alias": "Garden",
       "mode": "single",
       "triggers": [
        {
         "trigger": "state",
         "entity_id": "input_boolean.go",
         "to": "on",
         "id": "start"
        },
        {
         "trigger": "state",
         "entity_id": "input_boolean.stop",
         "to": "on",
         "id": "stop"
        }
       ],
       "conditions": [],
       "actions": [
        {
         "choose": [
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "start"
            },
            {
             "condition": "state",
             "entity_id": "input_boolean.enabled",
             "state": "on"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_on",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            },
            {
             "delay": {
              "seconds": 3
             }
            },
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          },
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "stop"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          }
         ]
        }
       ]
      },
      "trace": {
       "trigger/0": [
        {
         "path": "trigger/0",
         "timestamp": "2026-11-06T18:55:51.540223+00:00",
         "changed_variables": {
          "trigger": {
           "id": "start",
           "idx": "0",
           "platform": "state",
           "entity_id": "input_boolean.go",
           "description": "state of input_boolean.go"
          }
         }
        }
       ],
       "action/0": [
        {
         "path": "action/0",
         "timestamp": "2026-11-06T18:55:51.541859+00:00",
         "result": {
          "choice": 0
         }
        }
       ],
       "action/0/choose/0": [
        {
         "path": "action/0/choose/0",
         "timestamp": "2026-11-06T18:55:51.542189+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/0/conditions/0": [
        {
         "path": "action/0/choose/0/conditions/0",
         "timestamp": "2026-11-06T18:55:51.542223+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/0/conditions/1": [
        {
         "path": "action/0/choose/0/conditions/1",
         "timestamp": "2026-11-06T18:55:51.542251+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/0/conditions/1/entity_id/0": [
        {
         "path": "action/0/choose/0/conditions/1/entity_id/0",
         "timestamp": "2026-11-06T18:55:51.542265+00:00",
         "result": {
          "result": true,
          "state": "on",
          "wanted_state": "on"
         }
        }
       ],
       "action/0/choose/0/sequence/0": [
        {
         "path": "action/0/choose/0/sequence/0",
         "timestamp": "2026-11-06T18:55:51.545800+00:00",
         "result": {
          "params": {
           "domain": "input_boolean",
           "service": "turn_on",
           "service_data": {},
           "target": {
            "entity_id": [
             "input_boolean.valve"
            ]
           }
          },
          "running_script": false
         }
        }
       ],
       "action/0/choose/0/sequence/1": [
        {
         "path": "action/0/choose/0/sequence/1",
         "timestamp": "2026-11-06T18:55:51.547239+00:00",
         "result": {
          "delay": 3.0,
          "done": false
         }
        }
       ]
      }
     }
    }
   }
  },
  {
   "name": "garden finished: on, delay, off",
   "now": "2026-11-06T18:55:55.283820+00:00",
   "states": {
    "input_boolean.go": {
     "entity_id": "input_boolean.go",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.539163+00:00",
     "last_updated": "2026-11-06T18:55:51.539163+00:00",
     "attributes": {
      "friendly_name": "Go"
     }
    },
    "input_boolean.stop": {
     "entity_id": "input_boolean.stop",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.349550+00:00",
     "last_updated": "2026-11-06T18:55:51.349550+00:00",
     "attributes": {
      "friendly_name": "Stop"
     }
    },
    "input_boolean.enabled": {
     "entity_id": "input_boolean.enabled",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.537912+00:00",
     "last_updated": "2026-11-06T18:55:51.537912+00:00",
     "attributes": {
      "friendly_name": "Enabled"
     }
    },
    "input_boolean.valve": {
     "entity_id": "input_boolean.valve",
     "state": "off",
     "last_changed": "2026-11-06T18:55:54.558869+00:00",
     "last_updated": "2026-11-06T18:55:54.558869+00:00",
     "attributes": {
      "friendly_name": "Valve"
     }
    },
    "input_boolean.door": {
     "entity_id": "input_boolean.door",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.350570+00:00",
     "last_updated": "2026-11-06T18:55:51.350570+00:00",
     "attributes": {
      "friendly_name": "Door"
     }
    },
    "input_boolean.lamp": {
     "entity_id": "input_boolean.lamp",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.350861+00:00",
     "last_updated": "2026-11-06T18:55:51.350861+00:00",
     "attributes": {
      "friendly_name": "Lamp"
     }
    },
    "input_boolean.bell": {
     "entity_id": "input_boolean.bell",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.351105+00:00",
     "last_updated": "2026-11-06T18:55:51.351105+00:00",
     "attributes": {
      "friendly_name": "Bell"
     }
    },
    "automation.garden": {
     "entity_id": "automation.garden",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.404506+00:00",
     "last_updated": "2026-11-06T18:55:54.559878+00:00",
     "attributes": {
      "id": "garden",
      "last_triggered": "2026-11-06T18:55:51.541172+00:00",
      "mode": "single",
      "current": 0,
      "friendly_name": "Garden"
     }
    },
    "automation.porch": {
     "entity_id": "automation.porch",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.406793+00:00",
     "last_updated": "2026-11-06T18:55:51.406793+00:00",
     "attributes": {
      "id": "porch",
      "last_triggered": null,
      "mode": "single",
      "current": 0,
      "friendly_name": "Porch"
     }
    },
    "automation.bell": {
     "entity_id": "automation.bell",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.408589+00:00",
     "last_updated": "2026-11-06T18:55:51.408589+00:00",
     "attributes": {
      "id": "bell",
      "last_triggered": null,
      "mode": "single",
      "current": 0,
      "friendly_name": "Bell"
     }
    }
   },
   "runs": {
    "garden": {
     "list": {
      "last_step": "action/0/choose/0/sequence/2",
      "run_id": "77c9d60905aec1a002036786140493d7",
      "state": "stopped",
      "script_execution": "finished",
      "timestamp": {
       "start": "2026-11-06T18:55:51.540161+00:00",
       "finish": "2026-11-06T18:55:54.560472+00:00"
      },
      "domain": "automation",
      "item_id": "garden",
      "trigger": "state of input_boolean.go"
     },
     "get": {
      "run_id": "77c9d60905aec1a002036786140493d7",
      "state": "stopped",
      "script_execution": "finished",
      "last_step": "action/0/choose/0/sequence/2",
      "error": null,
      "timestamp": {
       "start": "2026-11-06T18:55:51.540161+00:00",
       "finish": "2026-11-06T18:55:54.560472+00:00"
      },
      "trigger": "state of input_boolean.go",
      "config": {
       "id": "garden",
       "alias": "Garden",
       "mode": "single",
       "triggers": [
        {
         "trigger": "state",
         "entity_id": "input_boolean.go",
         "to": "on",
         "id": "start"
        },
        {
         "trigger": "state",
         "entity_id": "input_boolean.stop",
         "to": "on",
         "id": "stop"
        }
       ],
       "conditions": [],
       "actions": [
        {
         "choose": [
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "start"
            },
            {
             "condition": "state",
             "entity_id": "input_boolean.enabled",
             "state": "on"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_on",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            },
            {
             "delay": {
              "seconds": 3
             }
            },
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          },
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "stop"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          }
         ]
        }
       ]
      },
      "trace": {
       "trigger/0": [
        {
         "path": "trigger/0",
         "timestamp": "2026-11-06T18:55:51.540223+00:00",
         "changed_variables": {
          "trigger": {
           "id": "start",
           "idx": "0",
           "platform": "state",
           "entity_id": "input_boolean.go",
           "description": "state of input_boolean.go"
          }
         }
        }
       ],
       "action/0": [
        {
         "path": "action/0",
         "timestamp": "2026-11-06T18:55:51.541859+00:00",
         "result": {
          "choice": 0
         }
        }
       ],
       "action/0/choose/0": [
        {
         "path": "action/0/choose/0",
         "timestamp": "2026-11-06T18:55:51.542189+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/0/conditions/0": [
        {
         "path": "action/0/choose/0/conditions/0",
         "timestamp": "2026-11-06T18:55:51.542223+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/0/conditions/1": [
        {
         "path": "action/0/choose/0/conditions/1",
         "timestamp": "2026-11-06T18:55:51.542251+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/0/conditions/1/entity_id/0": [
        {
         "path": "action/0/choose/0/conditions/1/entity_id/0",
         "timestamp": "2026-11-06T18:55:51.542265+00:00",
         "result": {
          "result": true,
          "state": "on",
          "wanted_state": "on"
         }
        }
       ],
       "action/0/choose/0/sequence/0": [
        {
         "path": "action/0/choose/0/sequence/0",
         "timestamp": "2026-11-06T18:55:51.545800+00:00",
         "result": {
          "params": {
           "domain": "input_boolean",
           "service": "turn_on",
           "service_data": {},
           "target": {
            "entity_id": [
             "input_boolean.valve"
            ]
           }
          },
          "running_script": false
         }
        }
       ],
       "action/0/choose/0/sequence/1": [
        {
         "path": "action/0/choose/0/sequence/1",
         "timestamp": "2026-11-06T18:55:51.547239+00:00",
         "result": {
          "delay": 3.0,
          "done": true
         }
        }
       ],
       "action/0/choose/0/sequence/2": [
        {
         "path": "action/0/choose/0/sequence/2",
         "timestamp": "2026-11-06T18:55:54.557204+00:00",
         "result": {
          "params": {
           "domain": "input_boolean",
           "service": "turn_off",
           "service_data": {},
           "target": {
            "entity_id": [
             "input_boolean.valve"
            ]
           }
          },
          "running_script": false
         }
        }
       ]
      }
     }
    }
   }
  },
  {
   "name": "garden triggered by start: its option's condition is false, nothing runs",
   "now": "2026-11-06T18:55:55.307543+00:00",
   "states": {
    "input_boolean.go": {
     "entity_id": "input_boolean.go",
     "state": "on",
     "last_changed": "2026-11-06T18:55:55.305470+00:00",
     "last_updated": "2026-11-06T18:55:55.305470+00:00",
     "attributes": {
      "friendly_name": "Go"
     }
    },
    "input_boolean.stop": {
     "entity_id": "input_boolean.stop",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.349550+00:00",
     "last_updated": "2026-11-06T18:55:51.349550+00:00",
     "attributes": {
      "friendly_name": "Stop"
     }
    },
    "input_boolean.enabled": {
     "entity_id": "input_boolean.enabled",
     "state": "off",
     "last_changed": "2026-11-06T18:55:55.303896+00:00",
     "last_updated": "2026-11-06T18:55:55.303896+00:00",
     "attributes": {
      "friendly_name": "Enabled"
     }
    },
    "input_boolean.valve": {
     "entity_id": "input_boolean.valve",
     "state": "off",
     "last_changed": "2026-11-06T18:55:54.558869+00:00",
     "last_updated": "2026-11-06T18:55:54.558869+00:00",
     "attributes": {
      "friendly_name": "Valve"
     }
    },
    "input_boolean.door": {
     "entity_id": "input_boolean.door",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.350570+00:00",
     "last_updated": "2026-11-06T18:55:51.350570+00:00",
     "attributes": {
      "friendly_name": "Door"
     }
    },
    "input_boolean.lamp": {
     "entity_id": "input_boolean.lamp",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.350861+00:00",
     "last_updated": "2026-11-06T18:55:51.350861+00:00",
     "attributes": {
      "friendly_name": "Lamp"
     }
    },
    "input_boolean.bell": {
     "entity_id": "input_boolean.bell",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.351105+00:00",
     "last_updated": "2026-11-06T18:55:51.351105+00:00",
     "attributes": {
      "friendly_name": "Bell"
     }
    },
    "automation.garden": {
     "entity_id": "automation.garden",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.404506+00:00",
     "last_updated": "2026-11-06T18:55:55.307193+00:00",
     "attributes": {
      "id": "garden",
      "last_triggered": "2026-11-06T18:55:55.306433+00:00",
      "mode": "single",
      "current": 0,
      "friendly_name": "Garden"
     }
    },
    "automation.porch": {
     "entity_id": "automation.porch",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.406793+00:00",
     "last_updated": "2026-11-06T18:55:51.406793+00:00",
     "attributes": {
      "id": "porch",
      "last_triggered": null,
      "mode": "single",
      "current": 0,
      "friendly_name": "Porch"
     }
    },
    "automation.bell": {
     "entity_id": "automation.bell",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.408589+00:00",
     "last_updated": "2026-11-06T18:55:51.408589+00:00",
     "attributes": {
      "id": "bell",
      "last_triggered": null,
      "mode": "single",
      "current": 0,
      "friendly_name": "Bell"
     }
    }
   },
   "runs": {
    "garden": {
     "list": {
      "last_step": "action/0/choose/1/conditions/0",
      "run_id": "a21c431acf4947c72b623509b5da67ad",
      "state": "stopped",
      "script_execution": "finished",
      "timestamp": {
       "start": "2026-11-06T18:55:55.305952+00:00",
       "finish": "2026-11-06T18:55:55.307234+00:00"
      },
      "domain": "automation",
      "item_id": "garden",
      "trigger": "state of input_boolean.go"
     },
     "get": {
      "run_id": "a21c431acf4947c72b623509b5da67ad",
      "state": "stopped",
      "script_execution": "finished",
      "last_step": "action/0/choose/1/conditions/0",
      "error": null,
      "timestamp": {
       "start": "2026-11-06T18:55:55.305952+00:00",
       "finish": "2026-11-06T18:55:55.307234+00:00"
      },
      "trigger": "state of input_boolean.go",
      "config": {
       "id": "garden",
       "alias": "Garden",
       "mode": "single",
       "triggers": [
        {
         "trigger": "state",
         "entity_id": "input_boolean.go",
         "to": "on",
         "id": "start"
        },
        {
         "trigger": "state",
         "entity_id": "input_boolean.stop",
         "to": "on",
         "id": "stop"
        }
       ],
       "conditions": [],
       "actions": [
        {
         "choose": [
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "start"
            },
            {
             "condition": "state",
             "entity_id": "input_boolean.enabled",
             "state": "on"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_on",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            },
            {
             "delay": {
              "seconds": 3
             }
            },
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          },
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "stop"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          }
         ]
        }
       ]
      },
      "trace": {
       "trigger/0": [
        {
         "path": "trigger/0",
         "timestamp": "2026-11-06T18:55:55.306000+00:00",
         "changed_variables": {
          "trigger": {
           "id": "start",
           "idx": "0",
           "platform": "state",
           "entity_id": "input_boolean.go",
           "description": "state of input_boolean.go"
          }
         }
        }
       ],
       "action/0": [
        {
         "path": "action/0",
         "timestamp": "2026-11-06T18:55:55.307000+00:00"
        }
       ],
       "action/0/choose/0": [
        {
         "path": "action/0/choose/0",
         "timestamp": "2026-11-06T18:55:55.307060+00:00",
         "result": {
          "result": false
         }
        }
       ],
       "action/0/choose/0/conditions/0": [
        {
         "path": "action/0/choose/0/conditions/0",
         "timestamp": "2026-11-06T18:55:55.307079+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/0/conditions/1": [
        {
         "path": "action/0/choose/0/conditions/1",
         "timestamp": "2026-11-06T18:55:55.307098+00:00",
         "result": {
          "result": false
         }
        }
       ],
       "action/0/choose/0/conditions/1/entity_id/0": [
        {
         "path": "action/0/choose/0/conditions/1/entity_id/0",
         "timestamp": "2026-11-06T18:55:55.307109+00:00",
         "result": {
          "result": false,
          "state": "off",
          "wanted_state": "on"
         }
        }
       ],
       "action/0/choose/1": [
        {
         "path": "action/0/choose/1",
         "timestamp": "2026-11-06T18:55:55.307141+00:00",
         "result": {
          "result": false
         }
        }
       ],
       "action/0/choose/1/conditions/0": [
        {
         "path": "action/0/choose/1/conditions/0",
         "timestamp": "2026-11-06T18:55:55.307150+00:00",
         "result": {
          "result": false
         }
        }
       ]
      }
     }
    }
   }
  },
  {
   "name": "garden triggered by stop: the stop option runs",
   "now": "2026-11-06T18:55:55.337201+00:00",
   "states": {
    "input_boolean.go": {
     "entity_id": "input_boolean.go",
     "state": "on",
     "last_changed": "2026-11-06T18:55:55.305470+00:00",
     "last_updated": "2026-11-06T18:55:55.305470+00:00",
     "attributes": {
      "friendly_name": "Go"
     }
    },
    "input_boolean.stop": {
     "entity_id": "input_boolean.stop",
     "state": "on",
     "last_changed": "2026-11-06T18:55:55.330048+00:00",
     "last_updated": "2026-11-06T18:55:55.330048+00:00",
     "attributes": {
      "friendly_name": "Stop"
     }
    },
    "input_boolean.enabled": {
     "entity_id": "input_boolean.enabled",
     "state": "off",
     "last_changed": "2026-11-06T18:55:55.303896+00:00",
     "last_updated": "2026-11-06T18:55:55.303896+00:00",
     "attributes": {
      "friendly_name": "Enabled"
     }
    },
    "input_boolean.valve": {
     "entity_id": "input_boolean.valve",
     "state": "off",
     "last_changed": "2026-11-06T18:55:54.558869+00:00",
     "last_updated": "2026-11-06T18:55:54.558869+00:00",
     "attributes": {
      "friendly_name": "Valve"
     }
    },
    "input_boolean.door": {
     "entity_id": "input_boolean.door",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.350570+00:00",
     "last_updated": "2026-11-06T18:55:51.350570+00:00",
     "attributes": {
      "friendly_name": "Door"
     }
    },
    "input_boolean.lamp": {
     "entity_id": "input_boolean.lamp",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.350861+00:00",
     "last_updated": "2026-11-06T18:55:51.350861+00:00",
     "attributes": {
      "friendly_name": "Lamp"
     }
    },
    "input_boolean.bell": {
     "entity_id": "input_boolean.bell",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.351105+00:00",
     "last_updated": "2026-11-06T18:55:51.351105+00:00",
     "attributes": {
      "friendly_name": "Bell"
     }
    },
    "automation.garden": {
     "entity_id": "automation.garden",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.404506+00:00",
     "last_updated": "2026-11-06T18:55:55.336113+00:00",
     "attributes": {
      "id": "garden",
      "last_triggered": "2026-11-06T18:55:55.331036+00:00",
      "mode": "single",
      "current": 0,
      "friendly_name": "Garden"
     }
    },
    "automation.porch": {
     "entity_id": "automation.porch",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.406793+00:00",
     "last_updated": "2026-11-06T18:55:51.406793+00:00",
     "attributes": {
      "id": "porch",
      "last_triggered": null,
      "mode": "single",
      "current": 0,
      "friendly_name": "Porch"
     }
    },
    "automation.bell": {
     "entity_id": "automation.bell",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.408589+00:00",
     "last_updated": "2026-11-06T18:55:51.408589+00:00",
     "attributes": {
      "id": "bell",
      "last_triggered": null,
      "mode": "single",
      "current": 0,
      "friendly_name": "Bell"
     }
    }
   },
   "runs": {
    "garden": {
     "list": {
      "last_step": "action/0/choose/1/sequence/0",
      "run_id": "b87e0ddaa537395d285e3502b95cbced",
      "state": "stopped",
      "script_execution": "finished",
      "timestamp": {
       "start": "2026-11-06T18:55:55.330499+00:00",
       "finish": "2026-11-06T18:55:55.336148+00:00"
      },
      "domain": "automation",
      "item_id": "garden",
      "trigger": "state of input_boolean.stop"
     },
     "get": {
      "run_id": "b87e0ddaa537395d285e3502b95cbced",
      "state": "stopped",
      "script_execution": "finished",
      "last_step": "action/0/choose/1/sequence/0",
      "error": null,
      "timestamp": {
       "start": "2026-11-06T18:55:55.330499+00:00",
       "finish": "2026-11-06T18:55:55.336148+00:00"
      },
      "trigger": "state of input_boolean.stop",
      "config": {
       "id": "garden",
       "alias": "Garden",
       "mode": "single",
       "triggers": [
        {
         "trigger": "state",
         "entity_id": "input_boolean.go",
         "to": "on",
         "id": "start"
        },
        {
         "trigger": "state",
         "entity_id": "input_boolean.stop",
         "to": "on",
         "id": "stop"
        }
       ],
       "conditions": [],
       "actions": [
        {
         "choose": [
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "start"
            },
            {
             "condition": "state",
             "entity_id": "input_boolean.enabled",
             "state": "on"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_on",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            },
            {
             "delay": {
              "seconds": 3
             }
            },
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          },
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "stop"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          }
         ]
        }
       ]
      },
      "trace": {
       "trigger/1": [
        {
         "path": "trigger/1",
         "timestamp": "2026-11-06T18:55:55.330538+00:00",
         "changed_variables": {
          "trigger": {
           "id": "stop",
           "idx": "1",
           "platform": "state",
           "entity_id": "input_boolean.stop",
           "description": "state of input_boolean.stop"
          }
         }
        }
       ],
       "action/0": [
        {
         "path": "action/0",
         "timestamp": "2026-11-06T18:55:55.331589+00:00",
         "result": {
          "choice": 1
         }
        }
       ],
       "action/0/choose/0": [
        {
         "path": "action/0/choose/0",
         "timestamp": "2026-11-06T18:55:55.331644+00:00",
         "result": {
          "result": false
         }
        }
       ],
       "action/0/choose/0/conditions/0": [
        {
         "path": "action/0/choose/0/conditions/0",
         "timestamp": "2026-11-06T18:55:55.331661+00:00",
         "result": {
          "result": false
         }
        }
       ],
       "action/0/choose/1": [
        {
         "path": "action/0/choose/1",
         "timestamp": "2026-11-06T18:55:55.331687+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/1/conditions/0": [
        {
         "path": "action/0/choose/1/conditions/0",
         "timestamp": "2026-11-06T18:55:55.331696+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/1/sequence/0": [
        {
         "path": "action/0/choose/1/sequence/0",
         "timestamp": "2026-11-06T18:55:55.333035+00:00",
         "result": {
          "params": {
           "domain": "input_boolean",
           "service": "turn_off",
           "service_data": {},
           "target": {
            "entity_id": [
             "input_boolean.valve"
            ]
           }
          },
          "running_script": false
         }
        }
       ]
      }
     }
    }
   }
  },
  {
   "name": "porch: the door is on, its for is counting, no run yet",
   "now": "2026-11-06T18:55:56.573619+00:00",
   "states": {
    "input_boolean.go": {
     "entity_id": "input_boolean.go",
     "state": "on",
     "last_changed": "2026-11-06T18:55:55.305470+00:00",
     "last_updated": "2026-11-06T18:55:55.305470+00:00",
     "attributes": {
      "friendly_name": "Go"
     }
    },
    "input_boolean.stop": {
     "entity_id": "input_boolean.stop",
     "state": "on",
     "last_changed": "2026-11-06T18:55:55.330048+00:00",
     "last_updated": "2026-11-06T18:55:55.330048+00:00",
     "attributes": {
      "friendly_name": "Stop"
     }
    },
    "input_boolean.enabled": {
     "entity_id": "input_boolean.enabled",
     "state": "off",
     "last_changed": "2026-11-06T18:55:55.303896+00:00",
     "last_updated": "2026-11-06T18:55:55.303896+00:00",
     "attributes": {
      "friendly_name": "Enabled"
     }
    },
    "input_boolean.valve": {
     "entity_id": "input_boolean.valve",
     "state": "off",
     "last_changed": "2026-11-06T18:55:54.558869+00:00",
     "last_updated": "2026-11-06T18:55:54.558869+00:00",
     "attributes": {
      "friendly_name": "Valve"
     }
    },
    "input_boolean.door": {
     "entity_id": "input_boolean.door",
     "state": "on",
     "last_changed": "2026-11-06T18:55:55.364578+00:00",
     "last_updated": "2026-11-06T18:55:55.364578+00:00",
     "attributes": {
      "friendly_name": "Door"
     }
    },
    "input_boolean.lamp": {
     "entity_id": "input_boolean.lamp",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.350861+00:00",
     "last_updated": "2026-11-06T18:55:51.350861+00:00",
     "attributes": {
      "friendly_name": "Lamp"
     }
    },
    "input_boolean.bell": {
     "entity_id": "input_boolean.bell",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.351105+00:00",
     "last_updated": "2026-11-06T18:55:51.351105+00:00",
     "attributes": {
      "friendly_name": "Bell"
     }
    },
    "automation.garden": {
     "entity_id": "automation.garden",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.404506+00:00",
     "last_updated": "2026-11-06T18:55:55.336113+00:00",
     "attributes": {
      "id": "garden",
      "last_triggered": "2026-11-06T18:55:55.331036+00:00",
      "mode": "single",
      "current": 0,
      "friendly_name": "Garden"
     }
    },
    "automation.porch": {
     "entity_id": "automation.porch",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.406793+00:00",
     "last_updated": "2026-11-06T18:55:51.406793+00:00",
     "attributes": {
      "id": "porch",
      "last_triggered": null,
      "mode": "single",
      "current": 0,
      "friendly_name": "Porch"
     }
    },
    "automation.bell": {
     "entity_id": "automation.bell",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.408589+00:00",
     "last_updated": "2026-11-06T18:55:51.408589+00:00",
     "attributes": {
      "id": "bell",
      "last_triggered": null,
      "mode": "single",
      "current": 0,
      "friendly_name": "Bell"
     }
    }
   },
   "runs": {
    "garden": {
     "list": {
      "last_step": "action/0/choose/1/sequence/0",
      "run_id": "b87e0ddaa537395d285e3502b95cbced",
      "state": "stopped",
      "script_execution": "finished",
      "timestamp": {
       "start": "2026-11-06T18:55:55.330499+00:00",
       "finish": "2026-11-06T18:55:55.336148+00:00"
      },
      "domain": "automation",
      "item_id": "garden",
      "trigger": "state of input_boolean.stop"
     },
     "get": {
      "run_id": "b87e0ddaa537395d285e3502b95cbced",
      "state": "stopped",
      "script_execution": "finished",
      "last_step": "action/0/choose/1/sequence/0",
      "error": null,
      "timestamp": {
       "start": "2026-11-06T18:55:55.330499+00:00",
       "finish": "2026-11-06T18:55:55.336148+00:00"
      },
      "trigger": "state of input_boolean.stop",
      "config": {
       "id": "garden",
       "alias": "Garden",
       "mode": "single",
       "triggers": [
        {
         "trigger": "state",
         "entity_id": "input_boolean.go",
         "to": "on",
         "id": "start"
        },
        {
         "trigger": "state",
         "entity_id": "input_boolean.stop",
         "to": "on",
         "id": "stop"
        }
       ],
       "conditions": [],
       "actions": [
        {
         "choose": [
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "start"
            },
            {
             "condition": "state",
             "entity_id": "input_boolean.enabled",
             "state": "on"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_on",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            },
            {
             "delay": {
              "seconds": 3
             }
            },
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          },
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "stop"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          }
         ]
        }
       ]
      },
      "trace": {
       "trigger/1": [
        {
         "path": "trigger/1",
         "timestamp": "2026-11-06T18:55:55.330538+00:00",
         "changed_variables": {
          "trigger": {
           "id": "stop",
           "idx": "1",
           "platform": "state",
           "entity_id": "input_boolean.stop",
           "description": "state of input_boolean.stop"
          }
         }
        }
       ],
       "action/0": [
        {
         "path": "action/0",
         "timestamp": "2026-11-06T18:55:55.331589+00:00",
         "result": {
          "choice": 1
         }
        }
       ],
       "action/0/choose/0": [
        {
         "path": "action/0/choose/0",
         "timestamp": "2026-11-06T18:55:55.331644+00:00",
         "result": {
          "result": false
         }
        }
       ],
       "action/0/choose/0/conditions/0": [
        {
         "path": "action/0/choose/0/conditions/0",
         "timestamp": "2026-11-06T18:55:55.331661+00:00",
         "result": {
          "result": false
         }
        }
       ],
       "action/0/choose/1": [
        {
         "path": "action/0/choose/1",
         "timestamp": "2026-11-06T18:55:55.331687+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/1/conditions/0": [
        {
         "path": "action/0/choose/1/conditions/0",
         "timestamp": "2026-11-06T18:55:55.331696+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/1/sequence/0": [
        {
         "path": "action/0/choose/1/sequence/0",
         "timestamp": "2026-11-06T18:55:55.333035+00:00",
         "result": {
          "params": {
           "domain": "input_boolean",
           "service": "turn_off",
           "service_data": {},
           "target": {
            "entity_id": [
             "input_boolean.valve"
            ]
           }
          },
          "running_script": false
         }
        }
       ]
      }
     }
    }
   }
  },
  {
   "name": "porch: the for ran out, the lamp is on",
   "now": "2026-11-06T18:55:59.110471+00:00",
   "states": {
    "input_boolean.go": {
     "entity_id": "input_boolean.go",
     "state": "on",
     "last_changed": "2026-11-06T18:55:55.305470+00:00",
     "last_updated": "2026-11-06T18:55:55.305470+00:00",
     "attributes": {
      "friendly_name": "Go"
     }
    },
    "input_boolean.stop": {
     "entity_id": "input_boolean.stop",
     "state": "on",
     "last_changed": "2026-11-06T18:55:55.330048+00:00",
     "last_updated": "2026-11-06T18:55:55.330048+00:00",
     "attributes": {
      "friendly_name": "Stop"
     }
    },
    "input_boolean.enabled": {
     "entity_id": "input_boolean.enabled",
     "state": "off",
     "last_changed": "2026-11-06T18:55:55.303896+00:00",
     "last_updated": "2026-11-06T18:55:55.303896+00:00",
     "attributes": {
      "friendly_name": "Enabled"
     }
    },
    "input_boolean.valve": {
     "entity_id": "input_boolean.valve",
     "state": "off",
     "last_changed": "2026-11-06T18:55:54.558869+00:00",
     "last_updated": "2026-11-06T18:55:54.558869+00:00",
     "attributes": {
      "friendly_name": "Valve"
     }
    },
    "input_boolean.door": {
     "entity_id": "input_boolean.door",
     "state": "on",
     "last_changed": "2026-11-06T18:55:55.364578+00:00",
     "last_updated": "2026-11-06T18:55:55.364578+00:00",
     "attributes": {
      "friendly_name": "Door"
     }
    },
    "input_boolean.lamp": {
     "entity_id": "input_boolean.lamp",
     "state": "on",
     "last_changed": "2026-11-06T18:55:58.370234+00:00",
     "last_updated": "2026-11-06T18:55:58.370234+00:00",
     "attributes": {
      "friendly_name": "Lamp"
     }
    },
    "input_boolean.bell": {
     "entity_id": "input_boolean.bell",
     "state": "off",
     "last_changed": "2026-11-06T18:55:51.351105+00:00",
     "last_updated": "2026-11-06T18:55:51.351105+00:00",
     "attributes": {
      "friendly_name": "Bell"
     }
    },
    "automation.garden": {
     "entity_id": "automation.garden",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.404506+00:00",
     "last_updated": "2026-11-06T18:55:55.336113+00:00",
     "attributes": {
      "id": "garden",
      "last_triggered": "2026-11-06T18:55:55.331036+00:00",
      "mode": "single",
      "current": 0,
      "friendly_name": "Garden"
     }
    },
    "automation.porch": {
     "entity_id": "automation.porch",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.406793+00:00",
     "last_updated": "2026-11-06T18:55:58.370349+00:00",
     "attributes": {
      "id": "porch",
      "last_triggered": "2026-11-06T18:55:58.367977+00:00",
      "mode": "single",
      "current": 0,
      "friendly_name": "Porch"
     }
    },
    "automation.bell": {
     "entity_id": "automation.bell",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.408589+00:00",
     "last_updated": "2026-11-06T18:55:51.408589+00:00",
     "attributes": {
      "id": "bell",
      "last_triggered": null,
      "mode": "single",
      "current": 0,
      "friendly_name": "Bell"
     }
    }
   },
   "runs": {
    "garden": {
     "list": {
      "last_step": "action/0/choose/1/sequence/0",
      "run_id": "b87e0ddaa537395d285e3502b95cbced",
      "state": "stopped",
      "script_execution": "finished",
      "timestamp": {
       "start": "2026-11-06T18:55:55.330499+00:00",
       "finish": "2026-11-06T18:55:55.336148+00:00"
      },
      "domain": "automation",
      "item_id": "garden",
      "trigger": "state of input_boolean.stop"
     },
     "get": {
      "run_id": "b87e0ddaa537395d285e3502b95cbced",
      "state": "stopped",
      "script_execution": "finished",
      "last_step": "action/0/choose/1/sequence/0",
      "error": null,
      "timestamp": {
       "start": "2026-11-06T18:55:55.330499+00:00",
       "finish": "2026-11-06T18:55:55.336148+00:00"
      },
      "trigger": "state of input_boolean.stop",
      "config": {
       "id": "garden",
       "alias": "Garden",
       "mode": "single",
       "triggers": [
        {
         "trigger": "state",
         "entity_id": "input_boolean.go",
         "to": "on",
         "id": "start"
        },
        {
         "trigger": "state",
         "entity_id": "input_boolean.stop",
         "to": "on",
         "id": "stop"
        }
       ],
       "conditions": [],
       "actions": [
        {
         "choose": [
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "start"
            },
            {
             "condition": "state",
             "entity_id": "input_boolean.enabled",
             "state": "on"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_on",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            },
            {
             "delay": {
              "seconds": 3
             }
            },
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          },
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "stop"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          }
         ]
        }
       ]
      },
      "trace": {
       "trigger/1": [
        {
         "path": "trigger/1",
         "timestamp": "2026-11-06T18:55:55.330538+00:00",
         "changed_variables": {
          "trigger": {
           "id": "stop",
           "idx": "1",
           "platform": "state",
           "entity_id": "input_boolean.stop",
           "description": "state of input_boolean.stop"
          }
         }
        }
       ],
       "action/0": [
        {
         "path": "action/0",
         "timestamp": "2026-11-06T18:55:55.331589+00:00",
         "result": {
          "choice": 1
         }
        }
       ],
       "action/0/choose/0": [
        {
         "path": "action/0/choose/0",
         "timestamp": "2026-11-06T18:55:55.331644+00:00",
         "result": {
          "result": false
         }
        }
       ],
       "action/0/choose/0/conditions/0": [
        {
         "path": "action/0/choose/0/conditions/0",
         "timestamp": "2026-11-06T18:55:55.331661+00:00",
         "result": {
          "result": false
         }
        }
       ],
       "action/0/choose/1": [
        {
         "path": "action/0/choose/1",
         "timestamp": "2026-11-06T18:55:55.331687+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/1/conditions/0": [
        {
         "path": "action/0/choose/1/conditions/0",
         "timestamp": "2026-11-06T18:55:55.331696+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/1/sequence/0": [
        {
         "path": "action/0/choose/1/sequence/0",
         "timestamp": "2026-11-06T18:55:55.333035+00:00",
         "result": {
          "params": {
           "domain": "input_boolean",
           "service": "turn_off",
           "service_data": {},
           "target": {
            "entity_id": [
             "input_boolean.valve"
            ]
           }
          },
          "running_script": false
         }
        }
       ]
      }
     }
    },
    "porch": {
     "list": {
      "last_step": "action/0",
      "run_id": "0eb6f6fe3210542d65f21f70b89273ce",
      "state": "stopped",
      "script_execution": "finished",
      "timestamp": {
       "start": "2026-11-06T18:55:58.367492+00:00",
       "finish": "2026-11-06T18:55:58.370380+00:00"
      },
      "domain": "automation",
      "item_id": "porch",
      "trigger": "state of input_boolean.door"
     },
     "get": {
      "run_id": "0eb6f6fe3210542d65f21f70b89273ce",
      "state": "stopped",
      "script_execution": "finished",
      "last_step": "action/0",
      "error": null,
      "timestamp": {
       "start": "2026-11-06T18:55:58.367492+00:00",
       "finish": "2026-11-06T18:55:58.370380+00:00"
      },
      "trigger": "state of input_boolean.door",
      "config": {
       "id": "porch",
       "alias": "Porch",
       "mode": "single",
       "triggers": [
        {
         "trigger": "state",
         "entity_id": "input_boolean.door",
         "to": "on",
         "for": {
          "seconds": 3
         }
        }
       ],
       "conditions": [],
       "actions": [
        {
         "action": "input_boolean.turn_on",
         "target": {
          "entity_id": "input_boolean.lamp"
         }
        }
       ]
      },
      "trace": {
       "trigger/0": [
        {
         "path": "trigger/0",
         "timestamp": "2026-11-06T18:55:58.367540+00:00",
         "changed_variables": {
          "trigger": {
           "id": "0",
           "idx": "0",
           "platform": "state",
           "entity_id": "input_boolean.door",
           "description": "state of input_boolean.door"
          }
         }
        }
       ],
       "action/0": [
        {
         "path": "action/0",
         "timestamp": "2026-11-06T18:55:58.368518+00:00",
         "result": {
          "params": {
           "domain": "input_boolean",
           "service": "turn_on",
           "service_data": {},
           "target": {
            "entity_id": [
             "input_boolean.lamp"
            ]
           }
          },
          "running_script": false
         }
        }
       ]
      }
     }
    }
   }
  },
  {
   "name": "bell: its action failed",
   "now": "2026-11-06T18:55:59.145502+00:00",
   "states": {
    "input_boolean.go": {
     "entity_id": "input_boolean.go",
     "state": "on",
     "last_changed": "2026-11-06T18:55:55.305470+00:00",
     "last_updated": "2026-11-06T18:55:55.305470+00:00",
     "attributes": {
      "friendly_name": "Go"
     }
    },
    "input_boolean.stop": {
     "entity_id": "input_boolean.stop",
     "state": "on",
     "last_changed": "2026-11-06T18:55:55.330048+00:00",
     "last_updated": "2026-11-06T18:55:55.330048+00:00",
     "attributes": {
      "friendly_name": "Stop"
     }
    },
    "input_boolean.enabled": {
     "entity_id": "input_boolean.enabled",
     "state": "off",
     "last_changed": "2026-11-06T18:55:55.303896+00:00",
     "last_updated": "2026-11-06T18:55:55.303896+00:00",
     "attributes": {
      "friendly_name": "Enabled"
     }
    },
    "input_boolean.valve": {
     "entity_id": "input_boolean.valve",
     "state": "off",
     "last_changed": "2026-11-06T18:55:54.558869+00:00",
     "last_updated": "2026-11-06T18:55:54.558869+00:00",
     "attributes": {
      "friendly_name": "Valve"
     }
    },
    "input_boolean.door": {
     "entity_id": "input_boolean.door",
     "state": "on",
     "last_changed": "2026-11-06T18:55:55.364578+00:00",
     "last_updated": "2026-11-06T18:55:55.364578+00:00",
     "attributes": {
      "friendly_name": "Door"
     }
    },
    "input_boolean.lamp": {
     "entity_id": "input_boolean.lamp",
     "state": "on",
     "last_changed": "2026-11-06T18:55:58.370234+00:00",
     "last_updated": "2026-11-06T18:55:58.370234+00:00",
     "attributes": {
      "friendly_name": "Lamp"
     }
    },
    "input_boolean.bell": {
     "entity_id": "input_boolean.bell",
     "state": "on",
     "last_changed": "2026-11-06T18:55:59.142530+00:00",
     "last_updated": "2026-11-06T18:55:59.142530+00:00",
     "attributes": {
      "friendly_name": "Bell"
     }
    },
    "automation.garden": {
     "entity_id": "automation.garden",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.404506+00:00",
     "last_updated": "2026-11-06T18:55:55.336113+00:00",
     "attributes": {
      "id": "garden",
      "last_triggered": "2026-11-06T18:55:55.331036+00:00",
      "mode": "single",
      "current": 0,
      "friendly_name": "Garden"
     }
    },
    "automation.porch": {
     "entity_id": "automation.porch",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.406793+00:00",
     "last_updated": "2026-11-06T18:55:58.370349+00:00",
     "attributes": {
      "id": "porch",
      "last_triggered": "2026-11-06T18:55:58.367977+00:00",
      "mode": "single",
      "current": 0,
      "friendly_name": "Porch"
     }
    },
    "automation.bell": {
     "entity_id": "automation.bell",
     "state": "on",
     "last_changed": "2026-11-06T18:55:51.408589+00:00",
     "last_updated": "2026-11-06T18:55:59.144872+00:00",
     "attributes": {
      "id": "bell",
      "last_triggered": "2026-11-06T18:55:59.143460+00:00",
      "mode": "single",
      "current": 0,
      "friendly_name": "Bell"
     }
    }
   },
   "runs": {
    "garden": {
     "list": {
      "last_step": "action/0/choose/1/sequence/0",
      "run_id": "b87e0ddaa537395d285e3502b95cbced",
      "state": "stopped",
      "script_execution": "finished",
      "timestamp": {
       "start": "2026-11-06T18:55:55.330499+00:00",
       "finish": "2026-11-06T18:55:55.336148+00:00"
      },
      "domain": "automation",
      "item_id": "garden",
      "trigger": "state of input_boolean.stop"
     },
     "get": {
      "run_id": "b87e0ddaa537395d285e3502b95cbced",
      "state": "stopped",
      "script_execution": "finished",
      "last_step": "action/0/choose/1/sequence/0",
      "error": null,
      "timestamp": {
       "start": "2026-11-06T18:55:55.330499+00:00",
       "finish": "2026-11-06T18:55:55.336148+00:00"
      },
      "trigger": "state of input_boolean.stop",
      "config": {
       "id": "garden",
       "alias": "Garden",
       "mode": "single",
       "triggers": [
        {
         "trigger": "state",
         "entity_id": "input_boolean.go",
         "to": "on",
         "id": "start"
        },
        {
         "trigger": "state",
         "entity_id": "input_boolean.stop",
         "to": "on",
         "id": "stop"
        }
       ],
       "conditions": [],
       "actions": [
        {
         "choose": [
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "start"
            },
            {
             "condition": "state",
             "entity_id": "input_boolean.enabled",
             "state": "on"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_on",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            },
            {
             "delay": {
              "seconds": 3
             }
            },
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          },
          {
           "conditions": [
            {
             "condition": "trigger",
             "id": "stop"
            }
           ],
           "sequence": [
            {
             "action": "input_boolean.turn_off",
             "target": {
              "entity_id": "input_boolean.valve"
             }
            }
           ]
          }
         ]
        }
       ]
      },
      "trace": {
       "trigger/1": [
        {
         "path": "trigger/1",
         "timestamp": "2026-11-06T18:55:55.330538+00:00",
         "changed_variables": {
          "trigger": {
           "id": "stop",
           "idx": "1",
           "platform": "state",
           "entity_id": "input_boolean.stop",
           "description": "state of input_boolean.stop"
          }
         }
        }
       ],
       "action/0": [
        {
         "path": "action/0",
         "timestamp": "2026-11-06T18:55:55.331589+00:00",
         "result": {
          "choice": 1
         }
        }
       ],
       "action/0/choose/0": [
        {
         "path": "action/0/choose/0",
         "timestamp": "2026-11-06T18:55:55.331644+00:00",
         "result": {
          "result": false
         }
        }
       ],
       "action/0/choose/0/conditions/0": [
        {
         "path": "action/0/choose/0/conditions/0",
         "timestamp": "2026-11-06T18:55:55.331661+00:00",
         "result": {
          "result": false
         }
        }
       ],
       "action/0/choose/1": [
        {
         "path": "action/0/choose/1",
         "timestamp": "2026-11-06T18:55:55.331687+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/1/conditions/0": [
        {
         "path": "action/0/choose/1/conditions/0",
         "timestamp": "2026-11-06T18:55:55.331696+00:00",
         "result": {
          "result": true
         }
        }
       ],
       "action/0/choose/1/sequence/0": [
        {
         "path": "action/0/choose/1/sequence/0",
         "timestamp": "2026-11-06T18:55:55.333035+00:00",
         "result": {
          "params": {
           "domain": "input_boolean",
           "service": "turn_off",
           "service_data": {},
           "target": {
            "entity_id": [
             "input_boolean.valve"
            ]
           }
          },
          "running_script": false
         }
        }
       ]
      }
     }
    },
    "porch": {
     "list": {
      "last_step": "action/0",
      "run_id": "0eb6f6fe3210542d65f21f70b89273ce",
      "state": "stopped",
      "script_execution": "finished",
      "timestamp": {
       "start": "2026-11-06T18:55:58.367492+00:00",
       "finish": "2026-11-06T18:55:58.370380+00:00"
      },
      "domain": "automation",
      "item_id": "porch",
      "trigger": "state of input_boolean.door"
     },
     "get": {
      "run_id": "0eb6f6fe3210542d65f21f70b89273ce",
      "state": "stopped",
      "script_execution": "finished",
      "last_step": "action/0",
      "error": null,
      "timestamp": {
       "start": "2026-11-06T18:55:58.367492+00:00",
       "finish": "2026-11-06T18:55:58.370380+00:00"
      },
      "trigger": "state of input_boolean.door",
      "config": {
       "id": "porch",
       "alias": "Porch",
       "mode": "single",
       "triggers": [
        {
         "trigger": "state",
         "entity_id": "input_boolean.door",
         "to": "on",
         "for": {
          "seconds": 3
         }
        }
       ],
       "conditions": [],
       "actions": [
        {
         "action": "input_boolean.turn_on",
         "target": {
          "entity_id": "input_boolean.lamp"
         }
        }
       ]
      },
      "trace": {
       "trigger/0": [
        {
         "path": "trigger/0",
         "timestamp": "2026-11-06T18:55:58.367540+00:00",
         "changed_variables": {
          "trigger": {
           "id": "0",
           "idx": "0",
           "platform": "state",
           "entity_id": "input_boolean.door",
           "description": "state of input_boolean.door"
          }
         }
        }
       ],
       "action/0": [
        {
         "path": "action/0",
         "timestamp": "2026-11-06T18:55:58.368518+00:00",
         "result": {
          "params": {
           "domain": "input_boolean",
           "service": "turn_on",
           "service_data": {},
           "target": {
            "entity_id": [
             "input_boolean.lamp"
            ]
           }
          },
          "running_script": false
         }
        }
       ]
      }
     }
    },
    "bell": {
     "list": {
      "last_step": "action/0",
      "run_id": "f791fd3d462dcaaa08d29d6fe621d85b",
      "state": "stopped",
      "script_execution": "error",
      "timestamp": {
       "start": "2026-11-06T18:55:59.142964+00:00",
       "finish": "2026-11-06T18:55:59.145213+00:00"
      },
      "domain": "automation",
      "item_id": "bell",
      "error": "Action notify.does_not_exist not found",
      "trigger": "state of input_boolean.bell"
     },
     "get": {
      "run_id": "f791fd3d462dcaaa08d29d6fe621d85b",
      "state": "stopped",
      "script_execution": "error",
      "last_step": "action/0",
      "error": "Action notify.does_not_exist not found",
      "timestamp": {
       "start": "2026-11-06T18:55:59.142964+00:00",
       "finish": "2026-11-06T18:55:59.145213+00:00"
      },
      "trigger": "state of input_boolean.bell",
      "config": {
       "id": "bell",
       "alias": "Bell",
       "mode": "single",
       "triggers": [
        {
         "trigger": "state",
         "entity_id": "input_boolean.bell",
         "to": "on"
        }
       ],
       "conditions": [],
       "actions": [
        {
         "action": "notify.does_not_exist",
         "data": {
          "message": "ding"
         }
        }
       ]
      },
      "trace": {
       "trigger/0": [
        {
         "path": "trigger/0",
         "timestamp": "2026-11-06T18:55:59.143004+00:00",
         "changed_variables": {
          "trigger": {
           "id": "0",
           "idx": "0",
           "platform": "state",
           "entity_id": "input_boolean.bell",
           "description": "state of input_boolean.bell"
          }
         }
        }
       ],
       "action/0": [
        {
         "path": "action/0",
         "timestamp": "2026-11-06T18:55:59.144051+00:00",
         "result": {
          "params": {
           "domain": "notify",
           "service": "does_not_exist",
           "service_data": {
            "message": "ding"
           },
           "target": {}
          },
          "running_script": false
         },
         "error": "Action notify.does_not_exist not found"
        }
       ]
      }
     }
    }
   }
  }
 ]
};
