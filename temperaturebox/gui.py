import glob
import json
import os
import re
import sys
import threading 
import time

import PySimpleGUI as sg
import serial
import minimalmodbus


def serial_ports():
    """ Lists serial port names

        :raises EnvironmentError:
            On unsupported or unknown platforms
        :returns:
            A list of the serial ports available on the system
    """
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')

    result = []
    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            result.append(port)
        except (OSError, serial.SerialException):
            pass
    return result

def extract_i(event):
    return int(re.match('\w+-([0-9]+)', event).groups()[0])

def get_instrument(port, address):
    instrument = minimalmodbus.Instrument(port, address)
    instrument.close_port_after_each_call = True
    return instrument
    # place more details here such as baud rate and parity    


def read_sv_pv(port, address):
    instrument = get_instrument(port, address)
    sv = instrument.read_register(0, 0, signed=True)/10.
    pv = instrument.read_register(1, 0, signed=True)/10.
    return sv, pv



def set_sv(value, port, address):
    instrument = get_instrument(port, address)
    instrument.write_register(0, value, 1, signed=True)
    return True


class Client(object):
    def __init__(self):
        """Client object which contains the GUI, logic and state of the temperature boxes
        The main thread is the window and interaction. Another thread controls the running of the protocols, querying of boxes an dwriting of data

        The settings are read from file and written on closing. The GUI is generated from the settings.

        The state of the boxes are tracked by the self.settings['boxes'] object
        """

        # load settings, these are saved and carried over from session to session
        with open('settings.json','r') as f:
            self.settings = json.load(f)

        # brute force list all serial ports
        self.ports = serial_ports()
        
        # create gui
        self.window = self.make_window()


    def check(self, event:str) -> None:
        """Check if the port and address are valid by trying to read the instrument

        Args:
            event (str): Event triggering the check, contains the box index
        """
        i = extract_i(event)
        box = self.settings['boxes'][i]
        sv, pv = read_sv_pv(box['port'], box['address'])
        self.window[f'checktext-{i}'].update(f'SV: {sv}\nPV: {pv}')


    def gen_protocol_list(self, ibox:int) -> list:
        """Generate a list of strings to populate the protcol multiline element

        Args:
            ibox (int): Box index

        Returns:
            list: List of strings descriping the protocol
        """
        box = self.settings['boxes'][ibox]
        return ["{step}: {temperature:0.2f} C for {time:0.2f} h".format(**p) for p in box['protocol']]


    def add_protocol_step(self, event:str, values:dict) -> None:
        """Add a protocol step to the box

        Args:
            event (str): Event triggering the addition, contains the box index
            values (dict): Dictionary of window values
        """
        i = extract_i(event)
        box = self.settings['boxes'][i]
        temperature = float(values[f'temperature-{i}'])
        time = float(values[f'time-{i}'])
        box['protocol'].append({'time':time, 'temperature':temperature, 'step':len(box['protocol'])+1})
        self.window[f'protocol-{i}'].update(self.gen_protocol_list(i))


    def clear_protocol(self, event:str) -> None:
        """Clear the protocol of a box

        Args:
            event (str): Even ttriggering the clear, contains the box index
        """
        i = extract_i(event)
        box = self.settings['boxes'][i]
        box['protocol'] = []
        self.window[f'protocol-{i}'].update(box['protocol'])


    def start_protocol(self, event:str, values:dict) -> None:
        """Mark a box for starting, the actual running of the protocol will occur in the .update_boxes method

        Args:
            event (str): Event triggering the start, contains the box index
            values (dict): Dictionary of window values
        """
        i = extract_i(event)
        box = self.settings['boxes'][i]
        basename = values[f'filename-{i}']
        box['state'].update({
            'basename': basename,
            'filepath': os.path.join(self.settings['data_directory'], basename+'.csv')})
        self.set_disabled(i, True, exceptions=[f'stop-{i}'])
        box['state']['status'] = 'starting'



    def set_disabled(self, i:int, disabled:bool, exceptions:list=[]) -> None:
        """Disables or enables the controls of a box

        Args:
            i (int): box index
            disabled (bool): Disable (or enable if False) the controls for the box
            exceptions (list, optional): List of keys of elements which won't be affected. Defaults to [].
        """
        # lock the interface
        suffix = f'-{i}'
        for element in self.window.element_list():
            if isinstance(element.key, str):
                if element.key.endswith(suffix):
                    if element.key not in exceptions:
                        try:
                            element.update(disabled=disabled)
                        except:
                            pass


    def stop_protocol(self, event:str) -> None:
        """Stop running a box protocol

        Args:
            event (str): the event triggering the stop, contains the box index
        """
        i = extract_i(event)
        box = self.settings['boxes'][i]
        # unlock the interface
        self.set_disabled(i, False)
        box['state']['status'] = 'stopped'
        self.window[f'status-{i}'].update('Status: stopped')



    def update_boxes(self) -> None:
        """All the functions that modify box['state'] should live within this function in order to avoid threads modifying the object 
        in an unpredictable manner
        """
        def start(box:dict):
            box['state'].update({
                'status':'running',
                'current_step':1,
                'start_timestamp':time.time(),
            })

            with open(box['state']['filepath'],'a') as f:
                f.write('timestamp, time_elapsed, pv, sv\n')
            
            start_step(box, 0)


        def start_step(box:dict, istep:int) -> None:
            new_sv = box['protocol'][istep]['temperature']
            set_sv(new_sv, box['port'], box['address'])

            box['state']['step_start_timestamp'] = time.time()
            update_datapoint(box)
            write_datapoint(box)
            update_status_gui(box)


        def update_datapoint(box:dict) -> None:
            # get time
            stamp = time.time()
            # read data
            sv, pv = read_sv_pv(box['port'], box['address'])
            # update internal data structure
            box['state'].update({
                'timestamp': stamp,
                'time_elapsed':stamp -  box['state']['start_timestamp'],
                'pv':pv,
                'sv':sv})

        def write_datapoint(box:dict) -> None:
            # write data to file
            with open(box['state']['filepath'],'a') as f:
                f.write('{timestamp}, {time_elapsed}, {pv:.2f}, {sv:.2f}\n'.format(**box['state']))
            
        def update_status_gui(box:dict) -> None:
            # update GUI
            step_hours = (box['state']['timestamp'] - box['state']['step_start_timestamp'])/3600
            start_hours = (box['state']['timestamp'] - box['state']['start_timestamp'])/3600
            status_text = \
'''Status: {status}
step: {current_step}
{start_hours:.2f}h ({step_hours:.2f}h)
SV: {sv:.2f}
PV: {pv:.2f}
'''.format(step_hours=step_hours, start_hours=start_hours, **box['state'])
            self.window.write_event_value(f'update-{i}', status_text)  # put a message into queue for GUI

        while True:
            for i,box in enumerate(self.settings['boxes']):
                if box['state']['status'] == 'starting':
                    start(box)

                if box['state']['status'] == 'running':
                    stamp = time.time()
                    if stamp - box['state']['timestamp'] > self.settings['read_delta']:
                        update_datapoint(box)
                        write_datapoint(box)
                        update_status_gui(box)

                    # Check to move on to next step
                    if stamp - box['state']['step_start_timestamp'] > box['protocol'][box['state']['current_step']-1]['time']*3600:
                        box['state']['current_step'] += 1

                        # There are no more steps, change status to done
                        if box['state']['current_step'] > len(box['protocol']):
                            box['state']['status'] = 'done'
                            self.window.write_event_value(f'update-{i}', 'Status: done')

                        # There are more steps, start a new step
                        else:
                            start_step(box, box['state']['current_step']-1)
            
            time.sleep(self.settings['sleep'])

    def make_window(self) -> sg.Window:
        self.layout = []
        for i, box in enumerate(self.settings['boxes']):
            self.layout.append(
                [sg.Frame(box['name'],
                    [[
                        sg.Frame('Connection',
                            [
                               [
                                    sg.Column(
                                        [
                                            [sg.Combo(self.ports, default_value=box['port'], key=f'port-{i}', size=(10,None), expand_x=True)],
                                            [sg.Combo(list(range(1,25)), default_value=box['address'], key=f'address-{i}',expand_x=True)],
                                            [sg.Button('Check', key=f'check-{i}', expand_x=True)]
                                        ]),
                                    sg.Text('SV:\nPV:', key=f'checktext-{i}', font='courier 10', size=(7,None))
                                ]
                            ]
                        ),
                        
                        sg.Frame('Protocol',
                            [
                                [
                                    sg.Column(
                                        [
                                            [sg.Text('Temperature (C)'), sg.Input('', tooltip='Enter temperature between 30C and 70C', key=f'temperature-{i}', size=(10,None))],
                                            [sg.Text('Time (h)'), sg.Input('', tooltip='Number of hours, put negative number for infinite time', key=f'time-{i}', size=(10,None), expand_x=True)],
                                            [sg.Button('Add',key=f'add-{i}'), sg.Button('Clear', key=f'clear-{i}')]
                                        ]
                                    ),                        
                                    sg.Listbox(values=self.gen_protocol_list(i), key=f'protocol-{i}',size=(30,4),font='courier 10')
                                ]
                            ]),
                        
                        sg.Frame('Control',
                            [
                                [
                                    sg.Column(
                                        [
                                            [sg.Input(box['state'].get('basename',''), tooltip='Filename', key=f'filename-{i}', size=(15,None), expand_x=True)],
                                            [sg.Button('Start', key=f'start-{i}'), sg.Button('Stop', key=f'stop-{i}')]
                                        ]
                                    ),
                                    sg.Text('Status\n\n\n\n', key=f'status-{i}', font='courier 10', size=(15,None))
                                ]
                            ])
                    ]], key=f'frame-{i}')
                ]
            )

        return sg.Window("Cyclikal Temperature Box Controller", self.layout, resizable=True, icon='./cyclikal_light_icon.ico')

    def run(self) -> None:
        """The main event loop for the GUI
        """
        threading.Thread(target=self.update_boxes, daemon=True).start()
        while True:  # Event Loop
            event, values = self.window.read()
            if event:
                if event.startswith('add-'):
                    self.add_protocol_step(event, values)
                elif event.startswith('clear-'):
                    self.clear_protocol(event)
                elif event.startswith('start-'):
                    self.start_protocol(event, values)
                elif event.startswith('stop-'):
                    self.stop_protocol(event)
                elif event.startswith('check-'):
                    self.check(event)
                elif event.startswith('update-'):
                    i = extract_i(event)
                    self.window[f'status-{i}'].update(values[event])

            if event == sg.WIN_CLOSED or event == 'Exit':
                with open('settings.json','w') as f:
                    json.dump(self.settings, f, sort_keys=True, indent=4)
                break

    def close(self) -> None:
        self.window.close()

def main():
    try:
        my_client = Client()
        my_client.run()
    except KeyboardInterrupt:
        print("\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
        print("Execution Interrupted From Console")
        my_client.close()

if __name__ == "__main__":
    main()
