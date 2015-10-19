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

# Delicode NI mate Cinema 4D Plugin v2.1
# http://ni-mate.com

import c4d
from c4d import gui,plugins
import os
import time
import socket
import math
import struct
from datetime import datetime
from datetime import timedelta

PLUGIN_ID = 1031182

UI_TAB_GROUP = 30000
UI_TAB_CREATE = 31000
UI_TAB_RECEIVE = 32000
UI_TAB_CONNECT = 33000

#Root
UI_ROOT_LINK_GROUP = 30500
UI_ROOT_LINK = 20001

#Create tab
UI_TAB_CREATE_HEADER = UI_TAB_CREATE+1
UI_TAB_CREATE_ENABLE_HELP = UI_TAB_CREATE+2
UI_TAB_CREATE_HELP_GROUP = UI_TAB_CREATE+3
UI_TAB_CREATE_HELP = UI_TAB_CREATE+4
UI_CREATE_NAME = UI_TAB_CREATE+5
UI_CREATE_BUTTON = UI_TAB_CREATE+6
UI_CREATE_HELP_TEXT = """Root objects are used to collect all received joint objects for easy manipulation. You can for example create different root objects for recording different actions.

You can change the current root object at any time by dragging an existing root object to the root object field or by creating a new root object from this tab.

The root object represents the depth sensor, so moving and rotating the root object correctly will allow a close match of the received locations in comparison to the real world.
"""

#Receive tab
UI_TAB_RECEIVE_HEADER = UI_TAB_RECEIVE+1
UI_TAB_RECEIVE_HEADER_TEXT = "Receive or record motion data under the root object:"
UI_TAB_RECEIVE_HEADER_NO_ROOT = "You must select a root object above to receive data!"
UI_PORT = 1001
UI_RUNBUTTON = 1003
UI_RECORDBUTTON = 1004
UI_START_TIME = 1008
UI_END_TIME = 1009
UI_DURATION = 1010
UI_CONNECT = 1011
UI_ZEROBUTTON = 1012
UI_DISCONNECT = 1013
UI_PREROLL = 1014
UI_SETZEROBUTTON = 1015
UI_APPLYZEROBUTTON = 1016
UI_TAB_RECEIVE_ENABLE_HELP = UI_TAB_RECEIVE+2
UI_TAB_RECEIVE_HELP_GROUP = UI_TAB_RECEIVE+3
UI_TAB_RECEIVE_HELP = UI_TAB_RECEIVE+4
UI_RECEIVE_HELP_TEXT = """Receive joint location and orientation data from NI mate. Note that the port must match the one in the NI mate skeleton tab. In order to receive both joint locations and rotations enable the "Basic + Orientation" OSC format from the NI mate "Full Skeleton" tab.

Starting normal receiving will listen to all data comming from NI mate and move the joint objects under the root object in real time accordingly. If the current root object doesn't have child objects with names corresponding to the received joint data these joint objects are created automatically.

Default pose
The joint objects are reset to the default pose (location and rotation) every time receiving or recording is stopped. You should try to match the default pose as closely as possible with your character's pose before connecting the capture objects to the character joints.
- "Receiving" the default pose will receive data from NI mate for 5 seconds and set the default pose to the last received data.
- "Setting" the default pose will set the current locations and rotations of the joint objects as the default pose.
- "Restoring" the default pose will set the joint objects to the default pose.

Recording
Recording will store the capture objects' motions as F-Curves starting from the specified starting time, and ending at the specified end time. Please note that:
- A duration of 0 seconds means the recording will go on untill it is manually stopped.
- Recording will always clear one second's worth of F-Curves in front of the current recording time in order to quarantee clean results.
- Preroll time is not recorded, but gives the user time to get into a good starting position before the actual recording is started.

Note: the default pose's 5 second receive time as well as the recording time will begin once the user is succesfully tracked for the first time and the first motion data is received from NI mate. The progress of the default pose receiving and recording can be monitored via the progress bar in the bottom left of the window.
"""

#Connect tab
UI_TAB_CONNECT_HEADER = UI_TAB_CONNECT+1
UI_TAB_CONNECT_HEADER_TEXT = "Connect the captured objects to other objects:"
UI_TAB_CONNECT_HEADER_NO_CHILDREN = "The selected root doesn't have any children to connect!"
UI_TAB_CONNECT_HEADER_NO_ROOT = "You must select a root object above to connect objects!"
UI_SCROLLAREA = UI_TAB_CONNECT+2
UI_ROOT_JOINTS_LIST = UI_TAB_CONNECT+3
UI_TAB_CONNECT_ENABLE_HELP = UI_TAB_CONNECT+4
UI_TAB_CONNECT_HELP_GROUP = UI_TAB_CONNECT+5
UI_TAB_CONNECT_HELP = UI_TAB_CONNECT+6
UI_CONNECT_HELP_TEXT = """Connect the received objects to other objects, for example the joints of a character:
1. Choose the objects to be connected to the selector boxes.
2. Use \"Connect all\" to create the needed PSR constraints for the objects or alternatively use the checkboxes next to the joint names to connect/disconnect the objects individually.

Notes on the created constraints:
The basic connecting only uses the joint rotations as using the locations would also mean that the target character's dimensions should match the captured person's dimensions exactly. However in practice this makes the character stay in place, so you should enable the joint position constraint for one of the joints (for example the body) by enabling the "P" checkbox in the joint constraint target properties.

After the joints have been constrained you can gain manual control of them by lowering the constraint's strength to 0 %. Animating the strength parameter between 100 % and 0 % allows for smooth transitions from motion captured data to manual animation.

Notes on rigging for motion capture:
The target character joints should follow a simple geometry starting from "Body":

Head
|
Neck
|-- Shoulders -- Elbows -- Hands
Body
|-- Hips -- Knees -- Feet

Correct orientation data is available for all joints except for hands and feet, so in general these should not be connected. Instead they will follow their parent joint's rotations by default and can be manually animated for better articulation.

All in all the character rig should be as simple as possible for the captured joints, but additional details (such as fingers) can of course be used after the simple structure in the skeleton chain.
"""

UI_ROOT_NAME = 2008

reset_locrot = False
start_time = 0.0
duration = 0.0
preroll = 0.0

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

def add_null(name, parent):
    ob = c4d.BaseObject(c4d.Onull)
    ob.SetName(name)
    ob.SetAbsScale(c4d.Vector(0.1, 0.1, 0.1))
    doc = c4d.documents.GetActiveDocument()
    doc.InsertObject(ob)
    
    child = parent.GetDown()
    while child is not None and child.GetName() < name:
        child = child.GetNext()

    if child is not None:
        ob.InsertBefore(child)
    else:
        ob.InsertUnderLast(parent)

    return ob

def add_default_pose(root):
    default_pose = c4d.BaseObject(c4d.Onull)
    default_pose.SetName("Default pose")
    doc = c4d.documents.GetActiveDocument()
    doc.InsertObject(default_pose)
    default_pose.InsertUnder(root)
    default_pose.SetEditorMode(c4d.MODE_OFF)
    default_pose.SetRenderMode(c4d.MODE_OFF)
    return default_pose

class NImateReceiver():
    original_rotations = {}
    original_locations = {}
    recording_started = {}
    cur_time = 0
    start_time = 0
    time_s = 0
    root_object = None
    default_pose = None
    record = False
    next_sync = False
    
    location_dict = {}
    rotation_dict = {}

    def run(self):
        global preroll
        global start_time
        global duration
		
        apply_location_dict = {}
        apply_rotation_dict = {}
        receive = True
        sync = False

        doc = c4d.documents.GetActiveDocument()
        
        try:
            data = self.sock.recv( 4096 )
        except:
            data = None
            
            if (self.next_sync):
                apply_location_dict = self.next_location_dict.copy()
                apply_rotation_dict = self.next_rotation_dict.copy()
                self.next_location_dict = {}
                self.next_rotation_dict = {}
                self.next_sync = False
                sync = True
        
            receive = False
        
        time_from_bundle = False
        
        trash = data
        while(receive):
            data = trash
            
            decoded = OSC.decodeOSC(data)
            ob_name = decoded[0]

            try:
                if(ob_name == "#bundle"):
                    time_from_bundle = True

                    if self.start_time == 0:
                        self.start_time = self.timestampToSeconds(decoded[1])
                        self.cur_time = self.start_time
                    else:
                        self.cur_time = self.timestampToSeconds(decoded[1])

                    while i < len(decoded):
                        ob_name = decoded[i]
                        num = len(decoded[i+1])

                        if(num == 3): #location
                            location_dict[ob_name] = ([decoded[i+2], decoded[i+3], decoded[i+4]])
                        elif(num == 4): #quaternion
                            rotation_dict[ob_name] = (decoded[i+2], decoded[i+3], decoded[i+4], decoded[i+5])
                        elif(num == 7): #location & quaternion
                            location_dict[ob_name] = (decoded[i+2], decoded[i+3], decoded[i+4])
                            rotation_dict[ob_name] = (decoded[i+5], decoded[i+6], decoded[i+7], decoded[i+8])

                        i = i + 2 + num
                else:
                    if len(decoded) == 3: #one value
                        if ob_name == "/NI_mate_sync":
                            if sync:
                                self.next_sync = True
                            else:
                                sync = True
                                apply_location_dict = self.location_dict.copy()
                                apply_rotation_dict = self.rotation_dict.copy()
                                self.location_dict = {}
                                self.rotation_dict = {}
                                self.next_location_dict = {}
                                self.next_rotation_dict = {}
                        else:
                            if sync:
                                self.next_location_dict[ob_name] = (decoded[2], 0, 0)
                            else:
                                self.location_dict[ob_name] = (decoded[2], 0, 0)
                    elif len(decoded) == 5: #location
                        if sync:
                            self.next_location_dict[ob_name] = (decoded[2], decoded[3], decoded[4])
                        else:
                            self.location_dict[ob_name] = (decoded[2], decoded[3], decoded[4])

                    elif len(decoded) == 6: #quaternion
                        if sync:
                            self.next_rotation_dict[ob_name] = (decoded[2], decoded[3], decoded[4], decoded[5])
                        else:
                            self.rotation_dict[ob_name] = (decoded[2], decoded[3], decoded[4], decoded[5])

                    elif len(decoded) == 9: #location & quaternion
                        if sync:
                            self.next_location_dict[ob_name] = (decoded[2], decoded[3], decoded[4])
                            self.next_rotation_dict[ob_name] = (decoded[2], decoded[3], decoded[4], decoded[5])
                        else:
                            self.location_dict[ob_name] = (decoded[2], decoded[3], decoded[4])
                            self.rotation_dict[ob_name] = (decoded[5], decoded[6], decoded[7], decoded[8])
            except Exception as ex:
                print("error parsing OSC message: " + str(decoded))
                print(ex)
                pass

            try:
                trash = self.sock.recv(1024)
            except:
                break
        
        if not time_from_bundle:
            if self.start_time == 0:
                self.start_time = datetime.now()
                self.cur_time = self.start_time
            else:
                self.cur_time = datetime.now()

        self.time_s = self.currentSeconds(self.cur_time)

        if self.record and self.time_s > preroll:
            doc.SetTime(c4d.BaseTime(self.time_s - preroll + start_time))       
            
        if sync:
            for joint_name, loc in apply_location_dict.items():
                joint = self.root_object.GetDown()

                while joint is not None and joint.GetName() != joint_name:
                    joint = joint.GetNext()

                if joint is None:
                    joint = add_null(joint_name, self.root_object)

                pos = c4d.Vector(100*loc[0], 100*loc[1], 100*loc[2])
                joint.SetAbsPos(pos)

                if self.record and self.time_s > preroll:
                    self.setLocationKey(joint, pos)

            for joint_name, quat in apply_rotation_dict.items():
                joint = self.root_object.GetDown()

                while joint is not None and joint.GetName() != joint_name:
                    joint = joint.GetNext()

                if joint is None:
                    joint = add_null(joint_name, self.root_object)

                hpb = c4d.utils.MatrixToHPB(self.quatToMat(quat))
                joint.SetAbsRot(c4d.Vector(hpb))

            if self.record and self.time_s > preroll:
                self.setRotationKey(joint, hpb)
                
            self.location_dict = {}
            self.rotation_dict = {}
        else:
            for joint_name, loc in self.location_dict.items():
                joint = self.root_object.GetDown()

                while joint is not None and joint.GetName() != joint_name:
                    joint = joint.GetNext()

                if joint is None:
                    joint = add_null(joint_name, self.root_object)

                pos = c4d.Vector(100*loc[0], 100*loc[1], 100*loc[2])
                joint.SetAbsPos(pos)

                if self.record and self.time_s > preroll:
                    self.setLocationKey(joint, pos)

            for joint_name, quat in self.rotation_dict.items():
                joint = self.root_object.GetDown()

                while joint is not None and joint.GetName() != joint_name:
                    joint = joint.GetNext()

                if joint is None:
                    joint = add_null(joint_name, self.root_object)

                hpb = c4d.utils.MatrixToHPB(self.quatToMat(quat))
                joint.SetAbsRot(c4d.Vector(hpb))

            if self.record and self.time_s > preroll:
                self.setRotationKey(joint, hpb)
        
        c4d.EventAdd()

    def ensure_default_pose(self):
        if self.default_pose is None:
            self.default_pose = self.root_object.GetDown()

            while self.default_pose is not None and self.default_pose.GetName() != "Default pose":
                self.default_pose = self.default_pose.GetNext()

            if self.default_pose is None:
                self.default_pose = add_default_pose(self.root_object)

    def ensure_default_object(self, joint):
        self.ensure_default_pose()

        d_ob = self.default_pose.GetDown()

        while d_ob is not None and d_ob.GetName() != joint.GetName():
            d_ob = d_ob.GetNext()

        if d_ob is None:
            d_ob = add_null(joint.GetName(), self.default_pose)

        return d_ob


    def __init__(self, UDP_PORT, record, root):
        self.sock = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setblocking(0)
        self.sock.bind( ("127.0.0.1", UDP_PORT) )

        self.original_locations = {}
        self.original_rotations = {}
        self.recording_started = {}
        self.time = 0
        self.start_time = 0
        self.time_s = 0
        self.record = record
        self.root_object = root

        self.default_pose = root.GetDown()

        while self.default_pose is not None and self.default_pose.GetName() != "Default pose":
            self.default_pose = self.default_pose.GetNext()

        if self.default_pose is not None:
            d_ob = self.default_pose.GetDown()

            while d_ob is not None:
                self.original_locations[d_ob.GetName()] = d_ob
                self.original_rotations[d_ob.GetName()] = d_ob
                d_ob = d_ob.GetNext()
        
        print("Delicode NI mate Plugin started listening to OSC on port " + str(UDP_PORT))
        
    def __del__(self):
        self.sock.close()
        print("Delicode NI mate Plugin stopped listening to OSC")

        global reset_locrot

        if reset_locrot:
            for joint_name, d_ob in self.original_locations.items():
                joint = self.root_object.GetDown()

                while joint is not None and joint.GetName() != joint_name:
                    joint = joint.GetNext()

                if joint is not None:
                    joint.SetAbsPos(d_ob.GetAbsPos())

            for joint_name, d_ob in self.original_rotations.items():
                joint = self.root_object.GetDown()

                while joint is not None and joint.GetName() != joint_name:
                    joint = joint.GetNext()

                if joint is not None:
                    joint.SetAbsRot(d_ob.GetAbsRot())
        else:
            default_pose = self.root_object.GetDown()

            while default_pose is not None and default_pose.GetName() != "Default pose":
                default_pose = default_pose.GetNext()

            if default_pose is None:
                default_pose = add_default_pose(self.root_object)

            joint = self.root_object.GetDown()

            while joint is not None:
                if joint != default_pose:
                    d_ob = default_pose.GetDown()

                    while d_ob is not None and d_ob.GetName() != joint.GetName():
                        d_ob = d_ob.GetNext()

                    if d_ob is None:
                        d_ob = add_null(joint.GetName(), default_pose)

                    d_ob.SetAbsPos(joint.GetAbsPos())
                    d_ob.SetAbsRot(joint.GetAbsRot())

                joint = joint.GetNext()

        c4d.EventAdd()

    def currentSeconds(self, t):
        if isinstance(t, datetime):
            td = t - self.start_time
            return td.days * 24 * 60 * 60 + td.seconds + td.microseconds / 1000000.0
        else:
            return ((t>>32) - (self.start_time>>32)) + (((float)(t&0xffffffff))/pow(2,32) - ((float)(self.start_time&0xffffffff))/pow(2,32))

    def setLocationKey(self,obj,pos):
        global preroll
        global start_time

        baset = c4d.BaseTime(self.time_s - preroll + start_time)
        baset1 = c4d.BaseTime(self.time_s - preroll + start_time + 1.0)

        id_trackX = c4d.DescID( c4d.DescLevel(c4d.ID_BASEOBJECT_POSITION, c4d.DTYPE_VECTOR, 0, ), c4d.DescLevel( c4d.VECTOR_X, c4d.DTYPE_REAL, 0))
        id_trackY = c4d.DescID( c4d.DescLevel(c4d.ID_BASEOBJECT_POSITION, c4d.DTYPE_VECTOR, 0, ), c4d.DescLevel( c4d.VECTOR_Y, c4d.DTYPE_REAL, 0))
        id_trackZ = c4d.DescID( c4d.DescLevel(c4d.ID_BASEOBJECT_POSITION, c4d.DTYPE_VECTOR, 0, ), c4d.DescLevel( c4d.VECTOR_Z, c4d.DTYPE_REAL, 0))

        track_ids = [id_trackX, id_trackY, id_trackZ]

        for i in xrange(3):
            track_id = track_ids[i]
            track = obj.FindCTrack(track_id)

            if track == None:
                track = c4d.CTrack(obj, track_id)
                obj.InsertTrackSorted(track);

            next_key = track.GetCurve().FindKey(baset, c4d.FINDANIM_RIGHT)
            while next_key != None and next_key["key"].GetTime() < baset1:
                track.GetCurve().DelKey(next_key["idx"])
                next_key = track.GetCurve().FindKey(baset, c4d.FINDANIM_RIGHT)

            key = track.GetCurve().AddKey(baset)['key']
            
            if i == 0:
                key.SetValue(track.GetCurve(), pos.x)
            elif i == 1:
                key.SetValue(track.GetCurve(), pos.y)
            else:
                key.SetValue(track.GetCurve(), pos.z)

        return True

    def quatToMat(self, q):
        ww = q[0]*q[0]
        xx = q[1]*q[1]
        yy = q[2]*q[2]
        zz = q[3]*q[3]
        xy = q[1]*q[2]
        xz = q[1]*q[3]
        yz = q[2]*q[3]
        wx = q[0]*q[1]
        wy = q[0]*q[2]
        wz = q[0]*q[3]

        x = c4d.Vector(1.0 - 2.0*(yy+zz), 2.0*(xy-wz), 2.0*(xz+wy))
        y = c4d.Vector(2.0*(xy+wz), 1.0 - 2.0*(xx+zz), 2.0*(yz-wx))
        z = c4d.Vector(2.0*(xz-wy), 2.0*(yz+wx), 1.0 - 2.0*(xx+yy))
        
        mat = c4d.Matrix(c4d.Vector(), x, y, z);

        return mat;

    def matToQuat(self, mat):
        m00 = mat.v1.x
        m01 = mat.v1.y
        m02 = mat.v1.z
        m10 = mat.v2.x
        m11 = mat.v2.y
        m12 = mat.v2.z
        m20 = mat.v3.x
        m21 = mat.v3.y
        m22 = mat.v3.z

        trace = (1.0 + m00 + m11 + m22)

        if trace > 0.00000001:
            s = 0.5/math.sqrt(trace)
            w = 0.25/s
            x = (m21-m12)*s
            y = (m02-m20)*s
            z = (m10-m01)*s

        else:
            if m00 > m11 and m00 > m22:
                s = 2.0 * math.sqrt(1.0 + m00 - m11 - m22)
                x = 0.25 * s

                s = 1.0/s
                w = (m21 - m12)*s
                y = (m10 + m01)*s
                z = (m20 + m02)*s
            elif m11 > m22:
                s = 2.0 * math.sqrt(1.0 + m11 - m00 - m22)
                y = 0.25 * s

                s = 1.0/s
                w = (m20 - m02)*s
                x = (m10 + m01)*s
                z = (m21 + m12)*s
            else:
                s = 2.0 * math.sqrt(1.0 + m22 - m00 - m11)
                z = 0.25 * s

                s = 1.0/s
                w = (m10 - m01)*s
                x = (m20 + m02)*s
                z = (m21 + m12)*s

        imag = 1.0/math.sqrt(w*w + x*x + y*y + z*z)

        return (w*imag, x*imag, y*imag, z*imag)

    def quatMul(self, q, r):
        w = r[0]*q[0] - r[1]*q[1] - r[2]*q[2] - r[3]*q[3]
        x = r[0]*q[1] + r[1]*q[0] - r[2]*q[3] + r[3]*q[2]
        y = r[0]*q[2] + r[1]*q[3] + r[2]*q[0] - r[3]*q[1]
        z = r[0]*q[3] - r[1]*q[2] + r[2]*q[1] + r[3]*q[0]

        return (w,x,y,z)

    def setRotationKey(self,obj,hpb):
        global preroll
        global start_time

        baset = c4d.BaseTime(self.time_s - preroll + start_time)
        baset1 = c4d.BaseTime(self.time_s - preroll + start_time + 1.0)

        id_trackX = c4d.DescID( c4d.DescLevel(c4d.ID_BASEOBJECT_ROTATION, c4d.DTYPE_VECTOR, 0, ), c4d.DescLevel( c4d.VECTOR_X, c4d.DTYPE_REAL, 0))
        id_trackY = c4d.DescID( c4d.DescLevel(c4d.ID_BASEOBJECT_ROTATION, c4d.DTYPE_VECTOR, 0, ), c4d.DescLevel( c4d.VECTOR_Y, c4d.DTYPE_REAL, 0))
        id_trackZ = c4d.DescID( c4d.DescLevel(c4d.ID_BASEOBJECT_ROTATION, c4d.DTYPE_VECTOR, 0, ), c4d.DescLevel( c4d.VECTOR_Z, c4d.DTYPE_REAL, 0))

        track_ids = [id_trackX, id_trackY, id_trackZ]

        for i in xrange(3):
            track_id = track_ids[i]
            track = obj.FindCTrack(track_id)

            if track == None:
                track = c4d.CTrack(obj, track_id)
                obj.InsertTrackSorted(track);

            if i == 0:
                new_rot = hpb.x
            elif i == 1:
                new_rot = hpb.y
            else:
                new_rot = hpb.z

            next_key = track.GetCurve().FindKey(baset, c4d.FINDANIM_RIGHT)
            while next_key != None and next_key["key"].GetTime() < baset1:
                track.GetCurve().DelKey(next_key["idx"])
                next_key = track.GetCurve().FindKey(baset, c4d.FINDANIM_RIGHT)

            prev_key = track.GetCurve().FindKey(baset, c4d.FINDANIM_LEFT)
            if prev_key is not None:
                prev_rot = prev_key["key"].GetValue()

                while new_rot - prev_rot > math.pi:
                    new_rot = new_rot - 2.0*math.pi

                while new_rot - prev_rot < -math.pi:
                    new_rot = new_rot + 2.0*math.pi

            key = track.GetCurve().AddKey(baset)['key']
            key.SetValue(track.GetCurve(), new_rot)

        return True

class NImateDialog(c4d.gui.GeDialog):
    links = {}
    link_indexes = {}
    link_boxes = {}

    def CreateLayout(self):
        self.SetTitle("Delicode NI mate receiver v2.0")

        self.GroupBegin(UI_ROOT_LINK_GROUP,c4d.BFH_SCALEFIT|c4d.BFV_FIT,2,0,"Root")
        #self.GroupBorder(c4d.BORDER_GROUP_TOP)
        self.GroupBorderSpace(10,10,10,10)
        self.AddStaticText(5,c4d.BFH_FIT,0,0,"Root",0)
        self.root_link = self.AddCustomGui(UI_ROOT_LINK, c4d.CUSTOMGUI_LINKBOX, "", c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT, 0, 0)
        self.GroupEnd()


        self.TabGroupBegin(UI_TAB_GROUP, c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT)

        self.GroupBegin(UI_TAB_CREATE, c4d.BFH_SCALEFIT|c4d.BFV_FIT, 1, 0, "Create")

        self.AddStaticText(UI_TAB_CREATE_HEADER,c4d.BFH_SCALEFIT|c4d.BFV_FIT,0,0,"Create a new root object or select an existing one above:",0)
        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)

        self.GroupBegin(UI_TAB_CREATE+10,c4d.BFH_SCALEFIT|c4d.BFV_FIT,2,0,"")
        self.GroupBorderSpace(10,10,10,10)
        self.AddStaticText(UI_TAB_CREATE+11,c4d.BFH_FIT,0,0,"Root name",0)
        self.AddEditText(UI_CREATE_NAME, c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT)
        self.GroupEnd()

        self.GroupBegin(UI_TAB_CREATE+20,c4d.BFH_SCALEFIT|c4d.BFV_FIT,2,0,"")
        self.createButton = self.AddButton(UI_CREATE_BUTTON,c4d.BFH_SCALE|c4d.BFV_SCALE, 150, 15, "Create")
        self.GroupEnd()

        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        self.AddCheckbox(UI_TAB_CREATE_ENABLE_HELP,c4d.BFH_FIT,0,0,"Show help")
        self.GroupBegin(UI_TAB_CREATE_HELP_GROUP, c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT,2,0,"")
        self.GroupEnd()

        self.GroupEnd() #Create


        self.GroupBegin(UI_TAB_RECEIVE, c4d.BFH_SCALEFIT|c4d.BFV_FIT, 1, 0, "Receive")

        self.AddStaticText(UI_TAB_RECEIVE_HEADER,c4d.BFH_SCALEFIT|c4d.BFV_FIT,0,0,UI_TAB_RECEIVE_HEADER_NO_ROOT,0)
        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)

        self.GroupBegin(UI_TAB_RECEIVE+10,c4d.BFH_SCALEFIT|c4d.BFV_FIT,3,0,"")
        self.GroupBorderSpace(10,10,10,10)
        self.AddStaticText(UI_TAB_RECEIVE+11,c4d.BFH_FIT,0,0,"Port",0)
        self.portNumber = self.AddEditNumberArrows(UI_PORT,c4d.BFH_SCALE)
        self.runButton = self.AddButton(UI_RUNBUTTON, c4d.BFH_SCALE|c4d.BFV_SCALE, 150, 15, "Start receiving")
        self.GroupEnd()

        self.GroupBegin(UI_TAB_RECEIVE+20, c4d.BFH_SCALEFIT|c4d.BFV_FIT, 3, 0, "Default pose")
        self.GroupBorder(c4d.BORDER_GROUP_TOP)
        self.GroupBorderSpace(10,10,10,10)
        self.zeroButton = self.AddButton(UI_ZEROBUTTON, c4d.BFH_SCALE|c4d.BFV_SCALE, 100, 15, "Receive")
        self.setZeroButton = self.AddButton(UI_SETZEROBUTTON, c4d.BFH_SCALE|c4d.BFV_SCALE, 100, 15, "Set")
        self.applyZeroButton = self.AddButton(UI_APPLYZEROBUTTON, c4d.BFH_SCALE|c4d.BFV_SCALE, 100, 15, "Restore")
        self.GroupEnd()

        self.GroupBegin(UI_TAB_RECEIVE+60,c4d.BFH_SCALEFIT|c4d.BFV_FIT,0,2,"Recording")
        self.GroupBorder(c4d.BORDER_GROUP_TOP)
        self.GroupBorderSpace(10,10,10,10)

        self.GroupBegin(UI_TAB_RECEIVE+60,c4d.BFH_SCALEFIT|c4d.BFV_FIT,6,3,"")
        
        self.AddStaticText(UI_TAB_RECEIVE+61, c4d.BFH_SCALEFIT, 0, 0, "Start", 0)
        self.startTime = self.AddEditNumberArrows(UI_START_TIME, c4d.BFH_SCALEFIT)
        self.AddStaticText(UI_TAB_RECEIVE+62, c4d.BFH_SCALEFIT, 0, 0, "s", 0)

        self.AddStaticText(UI_TAB_RECEIVE+63, c4d.BFH_SCALEFIT, 0, 0, "End", 0)
        self.endTime = self.AddEditNumberArrows(UI_END_TIME, c4d.BFH_SCALEFIT)
        self.AddStaticText(UI_TAB_RECEIVE+64, c4d.BFH_SCALEFIT, 0, 0, "s", 0)

        self.AddStaticText(UI_TAB_RECEIVE+65, c4d.BFH_SCALEFIT, 0, 0, "Duration", 0)
        self.duration = self.AddEditNumberArrows(UI_DURATION, c4d.BFH_SCALEFIT)
        self.AddStaticText(UI_TAB_RECEIVE+66, c4d.BFH_SCALEFIT, 0, 0, "s", 0)

        self.AddStaticText(UI_TAB_RECEIVE+65, c4d.BFH_SCALEFIT, 0, 0, "Preroll", 0)
        self.preroll = self.AddEditNumberArrows(UI_PREROLL, c4d.BFH_SCALEFIT)
        self.AddStaticText(UI_TAB_RECEIVE+66, c4d.BFH_SCALEFIT, 0, 0, "s", 0)

        self.GroupEnd()

        self.recordButton = self.AddButton(UI_RECORDBUTTON, c4d.BFH_SCALE|c4d.BFV_SCALE, 150, 15, "Start Recording")
        self.GroupEnd()

        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        self.AddCheckbox(UI_TAB_RECEIVE_ENABLE_HELP,c4d.BFH_FIT,0,0,"Show help")
        self.GroupBegin(UI_TAB_RECEIVE_HELP_GROUP, c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT,2,0,"")
        self.GroupEnd()

        self.GroupEnd() #Receiver


        self.GroupBegin(UI_TAB_CONNECT, c4d.BFH_SCALEFIT|c4d.BFV_FIT, 1, 0, "Connect")

        self.AddStaticText(UI_TAB_CONNECT_HEADER,c4d.BFH_SCALEFIT|c4d.BFV_FIT,0,0,UI_TAB_CONNECT_HEADER_NO_ROOT,0)
        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)

        self.ScrollGroupBegin(UI_SCROLLAREA, c4d.BFH_SCALEFIT|c4d.BFV_FIT, c4d.SCROLLGROUP_VERT, 150, 300)
        self.GroupBegin(UI_ROOT_JOINTS_LIST,c4d.BFH_SCALEFIT|c4d.BFV_FIT,3,0,"Joints")
        self.GroupBorder(c4d.BORDER_GROUP_TOP)
        self.GroupBorderSpace(10,10,10,10)
        self.AddStaticText(UI_TAB_CONNECT+1,c4d.BFH_SCALEFIT|c4d.BFV_FIT,0,0,"",0)
        self.GroupEnd();
        self.GroupEnd();

        self.GroupBegin(UI_TAB_CONNECT+10, c4d.BFH_SCALEFIT|c4d.BFV_FIT, 2, 0, "")
        self.connectButton = self.AddButton(UI_CONNECT,c4d.BFH_SCALE|c4d.BFV_SCALE, 150, 15, "Connect all")
        self.disconnectButton = self.AddButton(UI_DISCONNECT,c4d.BFH_SCALE|c4d.BFV_SCALE, 150, 15, "Disconnect all")
        self.GroupEnd();

        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        self.AddCheckbox(UI_TAB_CONNECT_ENABLE_HELP,c4d.BFH_FIT,0,0,"Show help")
        self.GroupBegin(UI_TAB_CONNECT_HELP_GROUP, c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT,2,0,"")
        self.GroupEnd()

        self.GroupEnd() #Connector

        self.GroupEnd() #tabgroup

        return True

    def InitValues(self):
        self.ServerStarted = False

        self.Enable(self.createButton, False)

        self.SetLong(UI_PORT, 7000, 1)
        self.Enable(self.runButton, False)
        self.Enable(self.zeroButton, False)
        self.Enable(self.setZeroButton, False)
        self.Enable(self.applyZeroButton, False)
        self.Enable(self.recordButton, False)

        self.Enable(self.connectButton, False)
        self.Enable(self.disconnectButton, False)

        return True

    def Timer(self, msg):
        run = True

        global reset_locrot
        if not reset_locrot:
            if self.receiver.time_s > 5:
                self.StopReceiving()
                self.SetString(self.zeroButton, "Receive")
                c4d.StatusClear()
                run = False
            else:
                if(self.receiver.time_s > 0):
                    self.SetString(self.zeroButton, "Cancel")
                    c4d.StatusSetBar(20.0 * self.receiver.time_s)
                
        elif self.receiver.record:
            pre = self.GetLong(UI_PREROLL)
            dur = self.GetLong(UI_DURATION)

            if self.receiver.time_s < pre:
                c4d.StatusSetBar(100.0*(pre - self.receiver.time_s)/pre)
            elif dur > 0:
                c4d.StatusSetBar(100.0*(self.receiver.time_s-pre)/dur);

                if self.receiver.time_s - pre > dur:
                    self.StopReceiving()
                    self.SetString(self.recordButton, "Start Recording")
                    c4d.StatusClear()
                    run = False
            else:
                c4d.StatusClear()

        if run:
            self.receiver.run()

    def getNextOb(self, ob):
        if ob==None: return None
 
        if ob.GetDown(): return ob.GetDown()
 
        while not ob.GetNext() and ob.GetUp():
            ob = ob.GetUp()
 
        return ob.GetNext()

    def CheckRoot(self):
        ob = self.root_link.GetLink()
        if ob is not None:
            self.SetString(UI_TAB_RECEIVE_HEADER, UI_TAB_RECEIVE_HEADER_TEXT)
            #todo - test if ob is an object

            self.Enable(self.runButton, True)
            self.Enable(self.recordButton, True)
            self.Enable(self.zeroButton, True)

            child = ob.GetDown();

            if child is not None:
                self.SetString(UI_TAB_CONNECT_HEADER, UI_TAB_CONNECT_HEADER_TEXT)
                self.Enable(self.connectButton, True)
                self.Enable(self.disconnectButton, True)
                self.Enable(self.setZeroButton, True)
                self.Enable(self.applyZeroButton, True)
            else:
                self.SetString(UI_TAB_CONNECT_HEADER, UI_TAB_CONNECT_HEADER_NO_CHILDREN)
                self.Enable(self.connectButton, False)
                self.Enable(self.disconnectButton, False)
                self.Enable(self.setZeroButton, False)
                self.Enable(self.applyZeroButton, False)

            self.links = {}
            self.link_boxes = {}
            self.link_indexes = {}

            self.LayoutFlushGroup(UI_ROOT_JOINTS_LIST)
            index = 100
            while child is not None:
                if child.GetName() == "Default pose":
                    child = child.GetNext()
                    continue

                self.link_boxes[child.GetName()] = self.AddCheckbox(index, c4d.BFH_FIT, 10, 10, "")
                self.Enable(self.link_boxes[child.GetName()], False)
                index = index+1
                self.AddStaticText(index,c4d.BFH_FIT,0,0,child.GetName(), 0)
                index = index+1
                self.links[child.GetName()] = self.AddCustomGui(index, c4d.CUSTOMGUI_LINKBOX, "", c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT, 0, 0)
                self.link_indexes[child.GetName()] = index;
                index = index+1
                child = child.GetNext()

            doc = c4d.documents.GetActiveDocument()
            cur_ob = doc.GetFirstObject()

            while cur_ob:
                for tag in cur_ob.GetTags():
                    if tag.GetName() == ob.GetName():
                        child = ob.GetDown()
                        while child is not None:
                            if tag[10001] == child:
                                self.links[child.GetName()].SetLink(cur_ob)
                                self.Enable(self.link_boxes[child.GetName()], True)
                                self.SetBool(self.link_boxes[child.GetName()], True)
                                break
                                
                            child = child.GetNext()

                cur_ob = self.getNextOb(cur_ob)

            self.LayoutChanged(UI_ROOT_JOINTS_LIST)
        else:
            self.SetString(UI_TAB_RECEIVE_HEADER, UI_TAB_RECEIVE_HEADER_NO_ROOT)
            self.SetString(UI_TAB_CONNECT_HEADER, UI_TAB_CONNECT_HEADER_NO_ROOT)
            self.Enable(self.connectButton, False)
            self.Enable(self.disconnectButton, False)
            self.Enable(self.runButton, False)
            self.Enable(self.recordButton, False)
            self.Enable(self.zeroButton, False)
            self.Enable(self.setZeroButton, False)
            self.Enable(self.applyZeroButton, False)

    def StopReceiving(self):
        self.SetTimer(0)
        self.ServerStarted = False
        del self.receiver
        self.Enable(self.portNumber, True)
        self.Enable(self.recordButton, True)
        self.Enable(self.runButton, True)
        self.Enable(UI_ROOT_LINK, True)
        self.Enable(self.connectButton, True)
        self.Enable(self.disconnectButton, True)
        self.Enable(self.zeroButton, True)
        self.CheckRoot()

    def StartReceiving(self, record):
        self.receiver = NImateReceiver(self.GetLong(UI_PORT), record, self.root_link.GetLink())
        self.SetTimer(10)
        self.ServerStarted = True
        self.Enable(self.portNumber, False)
        self.Enable(self.recordButton, False)
        self.Enable(self.runButton, False)
        self.Enable(UI_ROOT_LINK, False)
        self.Enable(self.connectButton, False)
        self.Enable(self.disconnectButton, False)
        self.Enable(self.zeroButton, False)
        self.Enable(self.setZeroButton, False)
        self.Enable(self.applyZeroButton, False)

    def Disconnect(self, link_key):
            root = self.root_link.GetLink()
            if root is not None:
                ob = self.links[link_key].GetLink()
                if ob is not None:
                    for tag in ob.GetTags():
                        if tag.GetName() == root.GetName():
                            tag.Remove()
                            break;
                
                    c4d.EventAdd()

    def addPSR(self, ob, name):
        tag = c4d.BaseTag(1019364)
        ob.InsertTag(tag)
        tag.SetName(name)
        tag[c4d.ID_CA_CONSTRAINT_TAG_PSR] = True
        tag[2100] = True
        tag[10005] = False
        return tag

    def Connect(self, link_key):
        root = self.root_link.GetLink()
        if root is not None:

            ob = self.links[link_key].GetLink()
            if ob is not None:
                tag = self.addPSR(ob, root.GetName())

                child = root.GetDown()
                while child is not None:
                    if child.GetName() == link_key:
                        tag[10001] = child
                        break
                    child = child.GetNext()
            
                c4d.EventAdd()

    def Command(self, id, msg):
        global reset_locrot
        global preroll
        global start_time
        global duration

        doc = c4d.documents.GetActiveDocument()
        self.frame = doc.GetTime().GetFrame(doc.GetFps())
        if id==UI_RUNBUTTON:
            reset_locrot = True

            if self.ServerStarted:
                self.StopReceiving()
                self.SetString(self.runButton, "Start receiving")
            else:
                self.StartReceiving(False)
                self.Enable(self.runButton, True)
                self.SetString(self.runButton, "Stop receiving")

        elif id==UI_RECORDBUTTON:
            reset_locrot = True
            preroll = self.GetLong(UI_PREROLL)
            start_time = self.GetLong(UI_START_TIME)
            duration = self.GetLong(UI_DURATION)

            if self.ServerStarted:
                self.StopReceiving()
                self.SetString(self.recordButton, "Start recording")
            else:
                self.StartReceiving(True)
                self.Enable(self.recordButton, True)
                self.SetString(self.recordButton, "Stop recording")

        elif id==UI_ZEROBUTTON:
            if self.ServerStarted:
                reset_locrot = True

                self.StopReceiving()
                self.SetString(self.zeroButton, "Receive")
            else:
                reset_locrot = False

                self.StartReceiving(False)
                self.Enable(self.zeroButton, True)
                self.SetString(self.zeroButton, "Waiting user")

        elif id==UI_SETZEROBUTTON:
            root = self.root_link.GetLink()

            default_pose = root.GetDown()

            while default_pose is not None and default_pose.GetName() != "Default pose":
                default_pose = default_pose.GetNext()

            if default_pose is None:
                default_pose = add_default_pose(root)

            joint = root.GetDown()

            while joint is not None:
                if joint != default_pose:
                    d_ob = default_pose.GetDown()

                    while d_ob is not None and d_ob.GetName() != joint.GetName():
                        d_ob = d_ob.GetNext()

                    if d_ob is None:
                        d_ob = add_null(joint.GetName(), default_pose)

                    d_ob.SetAbsPos(joint.GetAbsPos())
                    d_ob.SetAbsRot(joint.GetAbsRot())

                joint = joint.GetNext()

            c4d.EventAdd()

        elif id==UI_APPLYZEROBUTTON:
            root = self.root_link.GetLink()

            default_pose = root.GetDown()

            while default_pose is not None and default_pose.GetName() != "Default pose":
                default_pose = default_pose.GetNext()

            if default_pose is not None:
                d_ob = default_pose.GetDown()

                while d_ob is not None:
                    joint = root.GetDown()

                    while joint is not None and joint.GetName() != d_ob.GetName():
                        joint = joint.GetNext()

                    if joint is not None:
                        joint.SetAbsPos(d_ob.GetAbsPos())
                        joint.SetAbsRot(d_ob.GetAbsRot())

                    d_ob = d_ob.GetNext()

            c4d.EventAdd()

        elif id==UI_CONNECT:
            root = self.root_link.GetLink()
            if root is not None:
                first_child = root.GetDown()

                for key, value in self.links.items():
                    ob = value.GetLink()
                    if ob is not None and not self.GetBool(self.link_boxes[key]):
                        tag = self.addPSR(ob, root.GetName())

                        child = first_child
                        while child is not None:
                            if child.GetName() == key:
                                tag[10001] = child
                                self.SetBool(self.link_boxes[child.GetName()], True)
                                break
                            child = child.GetNext()
                    
                        c4d.EventAdd()

        elif id==UI_DISCONNECT:
            root = self.root_link.GetLink()
            if root is not None:
                for key, value in self.links.items():
                    ob = value.GetLink()
                    if ob is not None and self.GetBool(self.link_boxes[key]):

                        for tag in ob.GetTags():
                            if tag.GetName() == root.GetName():
                                self.SetBool(self.link_boxes[key], False)
                                tag.Remove()
                                break;
                    
                        c4d.EventAdd()

        elif id==UI_ROOT_LINK:
            self.CheckRoot()

        elif id==UI_CREATE_NAME:
            ob_name = self.GetString(UI_CREATE_NAME)
            self.Enable(self.createButton, ob_name != "")

        elif id==UI_CREATE_BUTTON:
            doc = c4d.documents.GetActiveDocument()
            ob_name = self.GetString(UI_CREATE_NAME)
            root_ob = c4d.BaseObject(c4d.Onull)
            root_ob.SetName(ob_name)
            doc.InsertObject(root_ob)
            self.root_link.SetLink(root_ob)
            c4d.EventAdd()
            self.CheckRoot()

        elif id==UI_START_TIME:
            sta = self.GetLong(UI_START_TIME)
            dur = self.GetLong(UI_DURATION)

            if(dur > 0):
                self.SetLong(UI_END_TIME, sta+dur)

        elif id==UI_DURATION:
            sta = self.GetLong(UI_START_TIME)
            dur = self.GetLong(UI_DURATION)

            if(dur > 0):
                self.SetLong(UI_END_TIME, sta+dur)
            else:
                self.SetLong(UI_END_TIME, 0)
                self.SetLong(UI_DURATION, 0)

        elif id==UI_END_TIME:
            sta = self.GetLong(UI_START_TIME)
            end = self.GetLong(UI_END_TIME)

            if(end <= sta):
                self.SetLong(UI_END_TIME, sta)
                self.SetLong(UI_DURATION, 0)
            else:
                self.SetLong(UI_DURATION, end-sta)

        elif id==UI_TAB_CREATE_ENABLE_HELP:
            self.LayoutFlushGroup(UI_TAB_CREATE_HELP_GROUP)
            if self.GetBool(UI_TAB_CREATE_ENABLE_HELP):
                self.AddMultiLineEditText(UI_TAB_CREATE_HELP, c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT, 0, 0, c4d.DR_MULTILINE_READONLY|c4d.DR_MULTILINE_WORDWRAP)
                self.SetString(UI_TAB_CREATE_HELP, UI_CREATE_HELP_TEXT)
            self.LayoutChanged(UI_TAB_CREATE_HELP_GROUP)

        elif id==UI_TAB_RECEIVE_ENABLE_HELP:
            self.LayoutFlushGroup(UI_TAB_RECEIVE_HELP_GROUP)
            if self.GetBool(UI_TAB_RECEIVE_ENABLE_HELP):
                self.AddMultiLineEditText(UI_TAB_RECEIVE_HELP, c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT, 0, 0, c4d.DR_MULTILINE_READONLY|c4d.DR_MULTILINE_WORDWRAP)
                self.SetString(UI_TAB_RECEIVE_HELP, UI_RECEIVE_HELP_TEXT)
            self.LayoutChanged(UI_TAB_RECEIVE_HELP_GROUP)

        elif id==UI_TAB_CONNECT_ENABLE_HELP:
            self.LayoutFlushGroup(UI_TAB_CONNECT_HELP_GROUP)
            if self.GetBool(UI_TAB_CONNECT_ENABLE_HELP):
                self.AddMultiLineEditText(UI_TAB_CONNECT_HELP, c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT, 0, 0, c4d.DR_MULTILINE_READONLY|c4d.DR_MULTILINE_WORDWRAP)
                self.SetString(UI_TAB_CONNECT_HELP, UI_CONNECT_HELP_TEXT)
            self.LayoutChanged(UI_TAB_CONNECT_HELP_GROUP)

        else:
            for key, value in self.link_indexes.items():
                if id == value:
                    if self.links[key].GetLink() == None:
                        self.Enable(self.link_boxes[key], False)
                        self.SetBool(self.link_boxes[key], False)
                    else:
                        self.Enable(self.link_boxes[key], True)

                elif id == value-2:
                    if self.GetBool(self.link_boxes[key]):
                        self.Connect(key)
                    else:
                        self.Disconnect(key)
 
        return True

class NImate2(c4d.plugins.CommandData):
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
    result = plugins.RegisterCommandPlugin(PLUGIN_ID, "NI mate receiver 2.0", 0, bmp, "Delicode NI mate receiver 2.0", NImate2())
