<img src="https://media.licdn.com/dms/image/C4D0BAQFwxfZMEa1yWw/company-logo_200_200/0/1613624395995?e=2147483647&v=beta&t=mPyrVVGwUXIrqHhJVrB2Jk_ncw70xMmr4moOpTnjlu4"  width="200" height="200" class = "center">  

![GitHub repo size](https://img.shields.io/github/repo-size/Cyclikal/temperature-box-controller)
![Website Status](https://img.shields.io/website-up-down-green-red/http/cyclikal.com.svg)  

![Language](https://img.shields.io/badge/Python-14354C?style=for-the-badge&logo=python&logoColor=white)

# Cyclikal Temperature-Box-Controller
This is a GUI for controling <a href="https://cyclikal.com/">Cyclikal</a> Temperature Boxes and logging their temperatures.

# Installation
Install requirements.
```bash 
pip install -r requirements.txt
```   

This will install `pyserial`, `minimalmodbus`, and the last open version of `pySimpleGUI`.

The `settings.json` file controls the behavior of the application, including:
- The number of panels in the GUI (`"boxes"`)
- The directory where the data is logged (`"data_directory"`). Note that if this directory must already exist.
- The minimum amount of time in seconds between logged datapoints (`"read_delta"`)
- The sleep time in seconds between checking the boxes (`"sleep"`)

A basic settings file for two boxes would look like this:
```json
{
    "data_directory":"./data",
    "read_delta":60,
    "sleep": 1.0,
    "boxes": [
        {
            "address": 1,
            "port": "COM6",
            "name": "Box 1",
            "protocol":[],
            "state":{"status":"unknown"}
        },
        {
            "address": 2,
            "port": "COM7",
            "name": "Box 2",
            "protocol":[],
            "state":{"status":"unknown"}
        }
    ]
}
```

Note that the `"protocol"` and the `"state"` will be populated by the application upon running. The `"address"` and the `"port"` can be changed in the GUI.
The application should work whether the boxes are connected by USB or RS485. The `"address"` parameter is the address set on the physical PID controller (Novus N1050). For RS485 communications the application assumes the controllers are set to a baudrate of 9600 and a parity of `None`.

# Usage
The application is launched by running the gui.py file in the `temperaturebox` folder:

```bash
python gui.py
```

The GUI provides a simple way to designate set temperatures and times for your Cyclikal temperature boxes and having the data logged in a simple CSV file.

# Common Gotchas
- The communication with the boxes fails due to the controllers not being set to baud 9.6 and Prty NONE. This can be changed on the physical PID controller (Novus 1050).
- The data does not get logged because the directory specified in the settings file does not exist.
- Getting a splash screen for paying for PySimpleGUI. This is solved by installing the last open version as specified in the `requirements.txt` file.

# Contributing 
Pull requests and bug reports are welcome.

# Licensing
MIT License

Copyright (c) 2024 Cyclikal, LLC


