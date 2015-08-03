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

# Delicode NI mate Cinema 4D Plugin v1.0
# http://www.ni-mate.com

import c4d
from c4d import gui,plugins
import os
import time
import socket
import math
import struct

PLUGIN_ID = 1028278

UI_PORT = 1001
UI_CREATE = 1002
UI_RUNBUTTON = 1003
UI_RECORD = 1004

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

class NImateReceiver():
    def run(self, create, record):
        doc = c4d.documents.GetActiveDocument()
        dict = {}
        
        try:
            data = self.sock.recv( 1024 )
        except:
            return True
        
        trash = data
        while(True):
            data = trash
            
            decoded = OSC.decodeOSC(data)
            if(len(decoded) == 5):
                dict[decoded[0]] = ([decoded[2], decoded[3], decoded[4]])
            
            try:
                trash = self.sock.recv(1024)
            except:
                break
            
        for key, value in dict.items():
            ob = doc.SearchObject(key)
            pos = c4d.Vector(-100*value[0], 100*value[1], 100*value[2])
            if ob is not None:
                ob.SetAbsPos(pos)

                if record:
                    self.setKey(ob, pos)

            elif create:
                ob = c4d.BaseObject(c4d.Onull)
                ob.SetName(key)
                doc.InsertObject(ob)
                ob.SetAbsPos(pos)

                if record:
                    self.setKey(ob, pos)

        c4d.EventAdd()


    def __init__(self, UDP_PORT):
        self.sock = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setblocking(0)
        self.sock.bind( ("localhost", UDP_PORT) )
        
        print("Delicode NI mate Plugin started listening to OSC on port " + str(UDP_PORT))
        
    def __del__(self):
        self.sock.close()
        print("Delicode NI mate Plugin stopped listening to OSC")

    def setKey(self,obj,pos):

        doc = c4d.documents.GetActiveDocument()
        fps = doc.GetFps()
        frame = doc.GetTime().GetFrame(fps)
        baset = doc.GetTime()
        trackX = None
        trackY = None
        trackZ = None
        tracks = obj.GetCTracks()

        if tracks != None:
            for track in tracks:
                if track.GetDescriptionID()[0].id == 903: #POSITION
                    if track.GetDescriptionID()[1].id == 1000: #X
                        trackX = track
                    if track.GetDescriptionID()[1].id == 1001: #Y
                        trackY = track
                    if track.GetDescriptionID()[1].id == 1002: #Z
                        trackZ = track

        if trackX == None:
            trackX = c4d.CTrack(obj, c4d.DescID( c4d.DescLevel(c4d.ID_BASEOBJECT_POSITION, c4d.DTYPE_VECTOR, 0, ), c4d.DescLevel( c4d.VECTOR_X, c4d.DTYPE_REAL, 0)))
            obj.InsertTrackSorted(trackX)
        if trackY == None:
            trackY = c4d.CTrack(obj, c4d.DescID( c4d.DescLevel(c4d.ID_BASEOBJECT_POSITION, c4d.DTYPE_VECTOR, 0, ), c4d.DescLevel( c4d.VECTOR_Y, c4d.DTYPE_REAL, 0)))
            obj.InsertTrackSorted(trackY)
        if trackZ == None:
            trackZ = c4d.CTrack(obj, c4d.DescID( c4d.DescLevel(c4d.ID_BASEOBJECT_POSITION, c4d.DTYPE_VECTOR, 0, ), c4d.DescLevel( c4d.VECTOR_Z, c4d.DTYPE_REAL, 0)))
            obj.InsertTrackSorted(trackZ)

        keyX = trackX.GetCurve().AddKey(baset)['key']
        keyX.SetValue(trackX.GetCurve(),pos.x)
        keyY = trackY.GetCurve().AddKey(baset)['key']
        keyY.SetValue(trackY.GetCurve(),pos.y)
        keyZ = trackZ.GetCurve().AddKey(baset)['key']
        keyZ.SetValue(trackZ.GetCurve(),pos.z)

        return True

class NImateDialog(c4d.gui.GeDialog):
    def CreateLayout(self):
        self.SetTitle("Delicode NI mate receiver v1.0")

        self.GroupBegin(20000,c4d.BFH_SCALEFIT|c4d.BFV_FIT,2,0,"")
        self.AddStaticText(0,c4d.BFH_FIT,0,0,"Port",0)
        self.portNumber = self.AddEditNumberArrows(UI_PORT,c4d.BFH_LEFT)
        self.AddCheckbox(UI_CREATE,c4d.BFH_FIT,0,0,"Create nulls based on received data")
        self.GroupEnd()

        self.GroupBegin(20002,c4d.BFH_SCALEFIT|c4d.BFV_FIT,2,0,"")
        self.AddCheckbox(UI_RECORD,c4d.BFH_FIT,0,0,"Record locations")
        self.GroupEnd()

        self.GroupBegin(20001,c4d.BFH_SCALEFIT|c4d.BFV_FIT,2,0,"")
        self.runButton = self.AddButton(UI_RUNBUTTON,c4d.BFH_SCALE|c4d.BFV_SCALE, 150, 15, "Start receiving")
        self.GroupEnd()

        self.SetLong(UI_PORT, 7000, 1)
        self.ServerStarted = False

        return True

    def Timer(self, msg):
        self.receiver.run(self.GetBool(UI_CREATE), self.GetBool(UI_RECORD))

    def Command(self, id, msg):
        doc = c4d.documents.GetActiveDocument()
        self.frame = doc.GetTime().GetFrame(doc.GetFps())
        if id==UI_RUNBUTTON:
            if self.ServerStarted:
                self.SetTimer(0)
                self.ServerStarted = False
                del self.receiver
                self.Enable(self.portNumber, True)
                self.SetString(self.runButton, "Start receiving")
            else:
                self.receiver = NImateReceiver(self.GetLong(UI_PORT))
                self.SetTimer(10)
                self.ServerStarted = True
                self.Enable(self.portNumber, False)
                self.SetString(self.runButton, "Stop receiving")
        return True

class NImate(c4d.plugins.CommandData):
    def Init(self, op):
        bc = op.GetData()
        bc.SetBool(UI_AUTORUN,False)
        op.SetData(bc)
        return True

    def Message(self, type, data):
        return True

    def Execute(self, doc):
        self.frame = doc.GetTime().GetFrame(doc.GetFps())
        if hasattr(self, 'dialog') == False:
            self.dialog = NImateDialog()

        return self.dialog.Open(dlgtype=c4d.DLG_TYPE_ASYNC, pluginid=PLUGIN_ID, defaultw=250, defaulth=100)

if __name__=='__main__':
    bmp = c4d.bitmaps.BaseBitmap()
    dir, file = os.path.split(__file__)
    fn = os.path.join(dir, "res", "Icon.tif")
    bmp.InitWith(fn)
    result = plugins.RegisterCommandPlugin(PLUGIN_ID, "NI mate receiver", 0, bmp, "Delicode NI mate receiver", NImate())