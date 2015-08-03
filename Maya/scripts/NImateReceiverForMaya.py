# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# Delicode NI mate Maya Plugin v2.0
# http://www.ni-mate.com

import maya.cmds as cmds
import maya.OpenMaya as om

from functools import partial
import socket
import sys
import os
import time
import threading
import math
import maya.utils as utils
import struct

preferences = None

class OSC():
    @staticmethod
    def readByte(data):
        length   = data.find(b'\x00')
        nextData = int(math.ceil((length+1) / 4.0) * 4)
        return (data[0:length], data[nextData:])

    @staticmethod
    def readString(data):
        length   = str(data).find("\0")
        nextData = int(math.ceil((length+1) / 4.0) * 4)
        return (data[0:length], data[nextData:])
    
    @staticmethod
    def readBlob(data):
        length   = struct.unpack(">i", data[0:4])[0]
        nextData = int(math.ceil((length) / 4.0) * 4) + 4
        return (data[4:length+4], data[nextData:])
    
    @staticmethod
    def readInt(data):
        if(len(data)<4):
            print("Error: too few bytes for int", data, len(data))
            rest = data
            integer = 0
        else:
            integer = struct.unpack(">i", data[0:4])[0]
            rest    = data[4:]
    
        return (integer, rest)
    
    @staticmethod
    def readLong(data):
        """Tries to interpret the next 8 bytes of the data
        as a 64-bit signed integer."""
        high, low = struct.unpack(">ll", data[0:8])
        big = (long(high) << 32) + low
        rest = data[8:]
        return (big, rest)
    
    @staticmethod
    def readDouble(data):
        """Tries to interpret the next 8 bytes of the data
        as a 64-bit double float."""
        floater = struct.unpack(">d", data[0:8])
        big = float(floater[0])
        rest = data[8:]
        return (big, rest)
    
    
    @staticmethod
    def readFloat(data):
        if(len(data)<4):
            print("Error: too few bytes for float", data, len(data))
            rest = data
            float = 0
        else:
            float = struct.unpack(">f", data[0:4])[0]
            rest  = data[4:]
    
        return (float, rest)
    
    @staticmethod
    def decodeOSC(data):
        table = { "i" : OSC.readInt, "f" : OSC.readFloat, "s" : OSC.readString, "b" : OSC.readBlob, "d" : OSC.readDouble }
        decoded = []
        address,  rest = OSC.readByte(data)
        typetags = ""
        
        if address == "#bundle":
            time, rest = readLong(rest)
            decoded.append(address)
            decoded.append(time)
            while len(rest)>0:
                length, rest = OSC.readInt(rest)
                decoded.append(OSC.decodeOSC(rest[:length]))
                rest = rest[length:]
    
        elif len(rest) > 0:
            typetags, rest = OSC.readByte(rest)
            decoded.append(address)
            decoded.append(typetags)
            
            if len(typetags) > 0:
                if typetags[0] == ',':
                    for tag in typetags[1:]:
                        value, rest = table[tag](rest)
                        decoded.append(value)
                else:
                    print("Oops, typetag lacks the magic")
    
        return decoded

class TimerObj(threading.Thread):
    def __init__(self, cmd):
        self.running = True
        self.command = cmd
        self.counter = 0
        threading.Thread.__init__(self)
        self.start()
        
    def __del__(self):
        self.running = False
        time.sleep(1.0/15.0)
        
    def run(self):
        while(self.running):
            time.sleep(1.0/30.0)
            utils.executeInMainThreadWithResult(self.command)

    def stop(self):
        self.running = False

class NImateReceiver():
    def run(self, create, record, scaling, createRoot, root_name):
        location_dict = {}
        rotation_dict = {}
        
        try:
            data = self.sock.recv( 1024 )
        except:
            return True
        trash = data
        
        while(True):
            data = trash
            decoded = OSC.decodeOSC(data)
            
            # Create root object for easier scaling
            if createRoot:
                if not root_name in cmds.ls(objectsOnly=True):
                    cmds.spaceLocator(name=root_name, position=(0,0,0))
            
            ob_name = str(decoded[0])
            
            if (len(decoded) == 5):     # location
                location_dict[ob_name] = ([decoded[2], decoded[3], decoded[4]])
            elif (len(decoded) == 6):   # quaternion
                rotation_dict[ob_name] = om.MQuaternion(decoded[3], decoded[4], decoded[5], decoded[2])
            elif (len(decoded) == 9):   # location & quaternion
                location_dict[ob_name] = ([decoded[2], decoded[3], decoded[4]])
                rotation_dict[ob_name] = om.MQuaternion(decoded[6], decoded[7], decoded[8], decoded[5])
            try:
                trash = self.sock.recv(1024)
            except:
                break
        
        # Handle locations
        for key, value in location_dict.items():
            if key in cmds.ls(objectsOnly=True):
                cmds.move(-value[0]*scaling, value[1]*scaling, value[2]*scaling, key, absolute=True, localSpace=True)
                if createRoot:
                    l = cmds.listRelatives(key, allParents=True)
                    if (l == None):
                        cmds.parent(key, root_name)
                if record:
                    cmds.setKeyframe(key, attribute='translateX')
                    cmds.setKeyframe(key, attribute='translateY')
                    cmds.setKeyframe(key, attribute='translateZ')
            elif create:
                cmds.spaceLocator(name=key, position=(0,0,0))
                cmds.move(-value[0]*scaling, value[1]*scaling, value[2]*scaling, key, absolute=True, localSpace=True)
                if createRoot:
                    l = cmds.listRelatives(key, allParents=True)
                    if (l == None):
                        cmds.parent(key, root_name)
                if record:
                    cmds.setKeyframe(key, attribute='translateX')
                    cmds.setKeyframe(key, attribute='translateY')
                    cmds.setKeyframe(key, attribute='translateZ')
        
        # Handle orientations
        for key, value in rotation_dict.items():
            if not key in cmds.ls(objectsOnly=True) and create:
                cmds.spaceLocator(name=key, position=(0,0,0))
            try:
                if createRoot:
                    l = cmds.listRelatives(key, allParents=True)
                    if (l == None):
                        cmds.parent(key, root_name)
                cmds.select(key)
                list = om.MSelectionList()
                om.MGlobal.getActiveSelectionList(list)
                obj = om.MObject()
                list.getDependNode( 0, obj )
                q = om.MQuaternion(value)
                xformFn = om.MFnTransform(obj)
                
                # Maya seems to dislike quaternions with w set to -0.00
                # This happens if orientation for a limb is not found
                if (value.w != -0.00):
                    xformFn.setRotationQuaternion(value.x, value.y, value.z, value.w) # space = MSpace::kTransform
                
                if record:
                    try:
                        cmds.setKeyframe(key, attribute='rotateX')
                        cmds.setKeyframe(key, attribute='rotateY')
                        cmds.setKeyframe(key, attribute='rotateZ')
                    except Warning as w:
                        print(w)
            except Exception as e:
                print(e)
                continue
        
        cmds.refresh(force=True)

    def __init__(self, UDP_PORT):
        self.sock = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setblocking(0)
        self.sock.bind( ("localhost", UDP_PORT) )
        
        print("-> Delicode NI mate receiver started listening to OSC on port " + str(UDP_PORT))
        
    def __del__(self):
        self.sock.close()
        print("-> Delicode NI mate receiver stopped listening to OSC")

    def setKey(self,obj,pos):
        return
        
class DelicodeNImatePreferences():
    def __init__(self, winName="NImateWindow"):
        self.winTitle = "Delicode NI mate"
        self.root_name = "nimate_root"
        self.winName = winName
        self.timer = False
        self.ServerStarted = False
        self.osc_port = 7000
        self.record = False
        self.create = False
        self.createRoot = False
        self.ui_osc_port = None
        self.scaling = 10
        
    def __del__(self):
        if self.ServerStarted:
            del self.timer
            del self.receiver

    def createUI(self):
        if cmds.window(self.winName, exists=True):
            cmds.deleteUI(self.winName)

        cmds.window(self.winName, title=self.winTitle, maximizeButton=False, minimizeButton=False, resizeToFitChildren=True)
        self.mainCol = cmds.columnLayout( adjustableColumn=True )
        
        cmds.gridLayout(numberOfRowsColumns=[2,2], cellWidthHeight=[120,20])
        cmds.text('OSC port')
        self.ui_oscport = cmds.intField(minValue=0, maxValue=65535, value=self.osc_port, changeCommand=partial(self.set_port), enable=not self.ServerStarted)
        cmds.text('Scale')
        self.ui_scaling = cmds.floatField(minValue=0, maxValue=1000, value=self.scaling, changeCommand=partial(self.set_scaling))
        cmds.setParent(upLevel=True)
        
        self.nullsbox = cmds.checkBox( value=self.create, label='Create locators based on received data', changeCommand=partial(self.set_create) )
        self.recbox = cmds.checkBox( value=self.record, label='Record motion capture', changeCommand=partial(self.set_record) )
        self.rootbox = cmds.checkBox(value=self.createRoot, label='Parent locators to a root object', changeCommand=partial(self.set_createRoot))
        
        
        if self.ServerStarted:
            self.receiveButton = cmds.button( label='Stop Receiving', command=partial(self.toggle_server) )
        else:
            self.receiveButton = cmds.button( label='Start Receiving', command=partial(self.toggle_server) )
        
        cmds.showWindow( self.winName )
        
    def set_port(self, arg=None):
        self.osc_port = cmds.intField(self.ui_oscport, query=True, value=True)
        
    def set_record(self, arg=None):
        self.record = cmds.checkBox(self.recbox, query=True, value=True)
        
    def set_create(self, arg=None):
        self.create = cmds.checkBox(self.nullsbox, query=True, value=True)
    
    def set_createRoot(self, arg=None):
        self.createRoot = cmds.checkBox(self.rootbox, query=True, value=True)
    
    def set_scaling(self, arg=None):
        self.scaling = cmds.floatField(self.ui_scaling, query=True, value=True)

    def toggle_server(self, arg=None):
        if self.ServerStarted:
            self.ServerStarted = False
            self.timer.stop()
            del self.timer
            del self.receiver
            
            if cmds.window(self.winName, exists=True):
                cmds.intField(self.ui_oscport, edit=True, enable=True)
                cmds.button(self.receiveButton, edit=True, label='Start Receiving')
            
            for name in cmds.lsUI(type='shelfButton'):
                if cmds.shelfButton(name, query=True, label=True) == 'NI mate receiver':
                    cmds.setParent('MayaWindow')
                    cmds.shelfButton(name, edit=True, enableBackground=False)
        else:
            self.receiver = NImateReceiver(self.osc_port)
            self.timer = TimerObj(self.timer_exec)
            self.ServerStarted = True
            
            if cmds.window(self.winName, exists=True):
                cmds.intField(self.ui_oscport, edit=True, enable=False)
                cmds.button(self.receiveButton, edit=True, label='Stop Receiving')
            
            for name in cmds.lsUI(type='shelfButton'):
                if cmds.shelfButton(name, query=True, label=True) == 'NI mate receiver':
                    cmds.setParent('MayaWindow')
                    if self.record:
                        cmds.shelfButton(name, edit=True, enableBackground=True, backgroundColor=(1,0,0))
                    else:
                        cmds.shelfButton(name, edit=True, enableBackground=True, backgroundColor=(0,0.667,1))

    
    def timer_exec(self):
        if self.ServerStarted:
            self.receiver.run(self.create, self.record, self.scaling, self.createRoot, self.root_name)

def showPreferences():
    global preferences
    if preferences == None:
        preferences = DelicodeNImatePreferences()
    preferences.createUI()
    
def toggleReceiver():
    global preferences
    if preferences == None:
        preferences = DelicodeNImatePreferences()
    preferences.toggle_server()
    
shelf = "Custom"

def setShelf(selected):
    global shelf
    shelf = selected

def shelfQuery():
    form = cmds.setParent(query=True)
    cmds.formLayout(form, edit=True, width=300)
    t = cmds.text(label="Select the shelf for NI mate receiver")
    m = cmds.optionMenu(label="Shelf", changeCommand=setShelf)
    for name in cmds.lsUI(type='shelfLayout'):
        cmds.menuItem(label=name)
    cr = cmds.button(label="Create", command='import maya.cmds as cmds\ncmds.layoutDialog(dismiss="Create")')
    ca = cmds.button(label="Cancel", command='import maya.cmds as cmds\ncmds.layoutDialog(dismiss="Cancel")')
    
    spacer = 5
    top = 5
    edge = 5
    cmds.formLayout(form, edit=True,
                                    attachForm=[(t, 'top', top), (t, 'left', edge), (t, 'right', edge), (m, 'left', edge), (m, 'right', edge), (cr, 'left', edge), (ca, 'right', edge)],
                                    attachNone=[(t, 'bottom'), (m, 'bottom'), (cr, 'bottom'), (ca, 'bottom')],
                                    attachControl=[(m, 'top', spacer, t), (cr, 'top', spacer, m), (ca, 'top', spacer, m)],
                                    attachPosition=[(cr, 'right', spacer, 50), (ca, 'left', spacer, 50)])

def create():
    global shelf

    if cmds.layoutDialog(ui=shelfQuery) == "Create":
        cmds.shelfTabLayout('ShelfLayout', edit=True, selectTab=shelf)
        cmds.shelfButton(label='NI mate receiver', parent=shelf, enableBackground=False, annotation='Start/Stop receiving data from NI mate, double click to access preferences.', image='NImateReceiverForMaya.ico', sourceType='python', command='import NImateReceiverForMaya\nNImateReceiverForMaya.toggleReceiver()', doubleClickCommand='import NImateReceiverForMaya\nNImateReceiverForMaya.showPreferences()')