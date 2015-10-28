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

bl_info = {
    "name": "Delicode NI mate Tools",
    "description": "Receives OSC and live feed data from the Delicode NI mate program",
    "author": "Janne Karhu (jahka), Jesse Kaukonen (gekko)", 
    "version": (2, 3),
    "blender": (2, 75, 0),
    "location": "View3D > Toolbar > NI mate Receiver & Game Engine",
    "category": "Animation",
    'wiki_url': '',
    'tracker_url': ''
    }

from mathutils import Vector
from mathutils import Matrix
from mathutils import Quaternion

import math
import struct
import socket
import subprocess, os
import mmap
import time

try:
    import bge
    GE = True
except ImportError:
    GE = False
    import bpy
    from bpy.props import *

add_rotations = False
reset_locrot = False

def set_GE_location(objects, ob_name, vec, originals):
    ob = objects.get(ob_name)
    
    if ob != None:
        ob.localPosition = 10*vec
        ob['time'] = -1

def set_GE_rotation(objects, ob_name, quat, originals):
    ob = objects.get(ob_name)
    
    if ob != None:
        if ob_name not in originals.keys():
            originals[ob_name] = ob.localOrientation.to_quaternion()

        if add_rotations:
            ob.localOrientation = quat * originals[ob_name]
        else:
            ob.localOrientation = quat

def set_location(objects, ob_name, vec, originals):
    if ob_name in objects.keys():
        if ob_name not in originals.keys():
            originals[ob_name] = objects[ob_name].location.copy()

        objects[ob_name].location = 10*vec
        
        if(bpy.context.scene.tool_settings.use_keyframe_insert_auto):
            objects[ob_name].keyframe_insert(data_path="location")

    elif bpy.context.scene.delicode_ni_mate_create != 'NONE':
        ob_type = bpy.context.scene.delicode_ni_mate_create
        if(ob_type == 'EMPTIES'):
            bpy.ops.object.add()
            bpy.context.object.empty_draw_size = 0.2
        elif(ob_type == 'SPHERES'):
            bpy.ops.mesh.primitive_ico_sphere_add()
        elif(ob_type == 'CUBES'):
            bpy.ops.mesh.primitive_cube_add()

        ob = bpy.context.object
        ob.name = ob_name
        ob.location = 10*vec

        if(bpy.context.scene.tool_settings.use_keyframe_insert_auto):
            objects[ob_name].keyframe_insert(data_path="location")

def set_rotation(objects, ob_name, quat, originals):
    if ob_name in objects.keys():
        objects[ob_name].rotation_mode = 'QUATERNION'

        if ob_name not in originals.keys():
            originals[ob_name] = objects[ob_name].rotation_quaternion.copy()

        if add_rotations:
            objects[ob_name].rotation_quaternion = quat * originals[ob_name]
        else:
            objects[ob_name].rotation_quaternion = quat
        
        if(bpy.context.scene.tool_settings.use_keyframe_insert_auto):
            objects[ob_name].keyframe_insert(data_path="rotation_quaternion")

def rotation_from_matrix(m00, m01, m02, m10, m11, m12, m20, m21, m22):
    mat = Matrix()
    mat[0][0] = m00
    mat[0][1] = m01
    mat[0][2] = m02
    mat[1][0] = m10
    mat[1][1] = m11
    mat[1][2] = m12
    mat[2][0] = m20
    mat[2][1] = m21
    mat[2][2] = m22

    return mat.to_quaternion()
            
class OSC():
    def readByte(data):
        length   = data.find(b'\x00')
        nextData = int(math.ceil((length+1) / 4.0) * 4)
        return (data[0:length], data[nextData:])

    
    def readString(data):
        length   = str(data).find("\0")
        nextData = int(math.ceil((length+1) / 4.0) * 4)
        return (data[0:length], data[nextData:])
    
    
    def readBlob(data):
        length   = struct.unpack(">i", data[0:4])[0]
        nextData = int(math.ceil((length) / 4.0) * 4) + 4
        return (data[4:length+4], data[nextData:])
    
    
    def readInt(data):
        if(len(data)<4):
            print("Error: too few bytes for int", data, len(data))
            rest = data
            integer = 0
        else:
            integer = struct.unpack(">i", data[0:4])[0]
            rest    = data[4:]
    
        return (integer, rest)
    
    
    def readLong(data):
        """Tries to interpret the next 8 bytes of the data
        as a 64-bit signed integer."""
        high, low = struct.unpack(">ll", data[0:8])
        big = (long(high) << 32) + low
        rest = data[8:]
        return (big, rest)
    
    
    def readDouble(data):
        """Tries to interpret the next 8 bytes of the data
        as a 64-bit double float."""
        floater = struct.unpack(">d", data[0:8])
        big = float(floater[0])
        rest = data[8:]
        return (big, rest)
    
    
    
    def readFloat(data):
        if(len(data)<4):
            print("Error: too few bytes for float", data, len(data))
            rest = data
            float = 0
        else:
            float = struct.unpack(">f", data[0:4])[0]
            rest  = data[4:]
    
        return (float, rest)
    
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
                if typetags[0] == ord(','):
                    for tag in typetags[1:]:
                        value, rest = table[chr(tag)](rest)
                        decoded.append(value)
                else:
                    print("Oops, typetag lacks the magic")
    
        return decoded

 
class NImateReceiver():
    original_rotations = {}
    original_locations = {}
    quit_port = None
    message_port = None
    profile_path = None
    
    location_dict = {}
    rotation_dict = {}
    
    next_location_dict = {}
    next_rotation_dict = {}
    next_sync = False

    def run(self, objects, set_location_func, set_rotation_func):
        
        apply_location_dict = {}
        apply_rotation_dict = {}
        
        receive = True
        
        sync = False
        
        try:
            data = self.sock.recv( 1024 )
        except:
            data = None

            if self.next_sync:            
                apply_location_dict = self.next_location_dict.copy()
                apply_rotation_dict = self.next_rotation_dict.copy()
                self.next_location_dict = {}
                self.next_rotation_dict = {}
                self.next_sync = False
                sync = True
            
            receive = False
            
        trash = data
        while(receive):
            data = trash
            
            decoded = OSC.decodeOSC(data)
            ob_name = str(decoded[0], "utf-8")
            
            try:
                if (ob_name.startswith("@")):
                    # Something to play with:
                    # values that begin with a @ are python expressions,
                    # and there is one parameter after the address in the OSC message
                    # if you set something such as
                    # bpy.data.objects"['Cube']".location.x= {V}
                    # into a OSC path for, say, a face shape smile controller you can move an object by smiling
                    to_evaluate = ob_name[1:]
                    to_evaluate += str(decoded[2])
                    try:
                        print(exec(to_evaluate))
                    except Exception as e:
                        print(to_evaluate)
                        print(str(e))
                elif (ob_name.startswith("?")):
                    # This one could be used for something such as mapping "thumbs up" gesture for rendering
                    # Add the following path to a gesture controller OSC path
                    # ?bpy.ops.render.render()
                    to_evaluate = ob_name[1:]
                    try:
                        print(exec(to_evaluate))
                    except Exception as e:
                        print(to_evaluate)
                        print(str(e))
                elif len(decoded) == 3: #one value
                    if ob_name == "NI_mate_sync":
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
                            self.next_location_dict[ob_name] = Vector([decoded[2], 0, 0])
                        else:
                            self.location_dict[ob_name] = Vector([decoded[2], 0, 0])

                elif len(decoded) == 5: #location
                    if sync:
                        self.next_location_dict[ob_name] = Vector([decoded[2], -decoded[4], decoded[3]])
                    else:
                        self.location_dict[ob_name] = Vector([decoded[2], -decoded[4], decoded[3]])

                elif len(decoded) == 6: #quaternion
                    if sync:
                        self.next_rotation_dict[ob_name] = Quaternion((-decoded[2], decoded[3], -decoded[5], decoded[4]))
                    else:
                        self.rotation_dict[ob_name] = Quaternion((-decoded[2], decoded[3], -decoded[5], decoded[4]))

                elif len(decoded) == 9: #location & quaternion
                    if sync:
                        self.next_location_dict[ob_name] = Vector([decoded[2], -decoded[4], decoded[3]])
                        self.next_rotation_dict[ob_name] = Quaternion((-decoded[5], decoded[6], -decoded[8], decoded[7]))
                    else:
                        self.location_dict[ob_name] = Vector([decoded[2], -decoded[4], decoded[3]])
                        self.rotation_dict[ob_name] = Quaternion((-decoded[5], decoded[6], -decoded[8], decoded[7]))
            except:
                print("Delicode NI mate Tools error parsing OSC message: " + str(decoded))
                pass
            
            try:
                trash = self.sock.recv(1024)
            except:
                break

        if sync:            
            for key, value in apply_location_dict.items():
                set_location_func(objects, key, value, self.original_locations)
            
            for key, value in apply_rotation_dict.items():
                set_rotation_func(objects, key, value, self.original_rotations)
            
            self.location_dict = {}
            self.rotation_dict = {}
        else:
            for key, value in self.location_dict.items():
                set_location_func(objects, key, value, self.location_dict)
                
            for key, value in self.rotation_dict.items():
                set_rotation_func(objects, key, value, self.rotation_dict)

    def __init__(self, UDP_PORT, QUIT_PORT):
        self.sock = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setblocking(0)
        self.sock.bind( ("127.0.0.1", UDP_PORT) )

        self.quit_port = QUIT_PORT

        self.original_rotations = {}
        self.original_locations = {}
        
        self.location_dict = {}
        self.rotation_dict = {}
        
        print("Delicode NI mate Tools started listening to OSC on port " + str(UDP_PORT))

    def __del__(self):
        self.sock.close()
        print("Delicode NI mate Tools stopped listening to OSC")

        if self.quit_port != None:
            if self.quit_port >= 0:
                try:
                    quit_sock = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )
                    quit_sock.sendto(b'/NI mate\x00\x00\x00\x00,s\x00\x00quit\x00\x00\x00\x00', ("127.0.0.1", self.quit_port) )

                    print("Quitting NI mate")
                except Exception as e:
                    print("Couldn't quit NI mate: %s" % e)
                    pass
        else:
            global reset_locrot
            if reset_locrot:
                for key, value in self.original_locations.items():
                    bpy.data.objects[key].location = value.copy()

                for key, value in self.original_rotations.items():
                    bpy.data.objects[key].rotation_quaternion = value.copy()

class DelicodeNImateFeed():
    image_texture = None
    file_map = None

    def run(self):
        from bge import texture
        
        if self.file_map != None:
            self.file_map.seek(0)

            w = 0
            h = 0

            if self.file_map.size() == 640*480*4:
                w = 640
                h = 480
            elif self.file_map.size() == 320*240*4:
                w = 320
                h = 240
            elif self.file_map.size() == 160*120*4:
                w = 160
                h = 120

            if w > 0 and h > 0:
                if self.img_w != w or self.img_h != h:
                    self.image_texture.source = texture.ImageBuff()
                    self.image_texture.source.filter = texture.FilterRGBA32()

                buf = self.file_map.read(w*h*4)
                self.image_texture.source.load(buf, w, h)
                self.image_texture.refresh(True)

    def __init__(self, image_name, sensor_num, feed_2):
        import sys
        import bge
        from bge import texture
        import tempfile

        cont = bge.logic.getCurrentController()
        own = cont.owner
        img_w = 0
        img_h = 0

        try:
            matID = texture.materialID(own, image_name)
        except:
            print("Delicode NI mate Tools Error: No texture with name: " + image_name)
            pass
        
        try:
            self.image_texture = texture.Texture(own, matID)

            filename = "NI_mate_shared_map"

            if feed_2:
                filename = filename + str(2*(sensor_num-1)+2)
            else:
                filename = filename + str(2*(sensor_num-1)+1)

            filename = filename + ".data"
        
            file = open(tempfile.gettempdir() + "/" + filename, "rb")
            if sys.platform.startswith('darwin') or sys.platform.startswith('Linux'):
                self.file_map = mmap.mmap(file.fileno(), 0, mmap.PROT_READ, mmap.ACCESS_READ)
            else:
                self.file_map = mmap.mmap(file.fileno(), 0, None, mmap.ACCESS_READ)
            file.close()

            self.file_map.seek(0)

            w = 0
            h = 0

            if self.file_map.size() == 640*480*4:
                w = 640
                h = 480
            elif self.file_map.size() == 320*240*4:
                w = 320
                h = 240
            elif self.file_map.size() == 160*120*4:
                w = 160
                h = 120

            if w > 0 and h > 0:
                buf = self.file_map.read(w*h*4)

                self.image_texture.source = texture.ImageBuff()
                self.image_texture.source.filter = texture.FilterRGBA32()
                self.image_texture.source.load(buf, w, h)

                self.img_w = w
                self.img_h = h

            if feed_2:
                print("Delicode NI mate Tools replacing " + image_name + " with sensor " + str(sensor_num) + " live feed 2")
            else:
                print("Delicode NI mate Tools replacing " + image_name + " with sensor " + str(sensor_num) + " live feed 1")
        except Exception as e:
            print("Delicode NI mate Tools Error: Couldn't open NI mate feed " + tempfile.gettempdir() + "/" + filename)
            print("Reason: %s" % e)
            self.file_map = None
            pass

if not GE:
    class DelicodeNImateFeedPlaneCreate(bpy.types.Operator):
        bl_idname = "wm.delicode_ni_mate_feed_plane_create"
        bl_label = "Create feed plane"
        bl_description = "Create a new plane for NI mate live feed"
        bl_options = {'REGISTER'}
        
        def execute(self, context):
            bpy.ops.mesh.primitive_plane_add()
            plane = context.object
            plane.scale = Vector((4.0/3.0, 1.0, 1.0))

            feed_prefix = "NImateFeed" + str(2*(context.scene.delicode_ni_mate_sensor-1) + (context.scene.delicode_ni_mate_feed == 'FEED2') + 1)

            plane.name = feed_prefix + "_Plane"
            
            if (feed_prefix + "_Image") not in bpy.data.images:
                bpy.ops.image.new(name=feed_prefix + "_Image", width=640, height=480, generated_type='UV_GRID')
            
            bpy.ops.mesh.uv_texture_add()
            plane.data.uv_textures[0].data[0].image = bpy.data.images[feed_prefix + "_Image"]

            mat = bpy.data.materials.new(feed_prefix + "_Material")
            mat.use_shadeless = True
            mat.use_transparency = True
            mat.alpha = 0.0

            tex = bpy.data.textures.new(feed_prefix + "_Texture", type = 'IMAGE')
            tex.image = bpy.data.images[feed_prefix + "_Image"]

            mtex = mat.texture_slots.add()
            mtex.texture = tex
            mtex.texture_coords = 'UV'
            mtex.use_map_alpha = True

            plane.data.materials.append(mat)
            
            bpy.ops.logic.sensor_add(name='SNImateFeed')
            plane.game.sensors['SNImateFeed'].use_pulse_true_level = True
            
            bpy.ops.logic.controller_add(name='CNImateFeed', type='PYTHON')
            plane.game.controllers['CNImateFeed'].mode = 'MODULE'
            plane.game.controllers['CNImateFeed'].module = 'animation_delicode_ni_mate_tools.updateFeed'
            plane.game.sensors['SNImateFeed'].link(plane.game.controllers['CNImateFeed'])
            
            bpy.ops.object.game_property_new(type='STRING', name='NImateFeedImage')
            plane.game.properties['NImateFeedImage'].value = feed_prefix + "_Image"
            context.scene.delicode_ni_mate_feed_image = feed_prefix + "_Image"
            
            bpy.ops.object.game_property_new(type='BOOL', name='NImateUseFeed2')
            plane.game.properties['NImateUseFeed2'].value = (context.scene.delicode_ni_mate_feed == 'FEED2')

            bpy.ops.object.game_property_new(type='INT', name='NImateUseSensor')
            plane.game.properties['NImateUseSensor'].value = context.scene.delicode_ni_mate_sensor
            
            return {'FINISHED'}
        
    class DelicodeNImateFeedLogicCreate(bpy.types.Operator):
        bl_idname = "wm.delicode_ni_mate_feed_logic_create"
        bl_label = "Create game logic"
        bl_description = "Create or update game logic to replace an image with NI mate live feed for the selected object"
        bl_options = {'REGISTER'}

        @classmethod
        def poll(self, context):
            return context.object != None
        
        def execute(self, context):
            ob = context.object

            if 'SNImateFeed' not in ob.game.sensors:
                bpy.ops.logic.sensor_add(name='SNImateFeed')
            ob.game.sensors['SNImateFeed'].use_pulse_true_level = True
            
            if 'CNImateFeed' not in ob.game.controllers:
                bpy.ops.logic.controller_add(name='CNImateFeed', type='PYTHON')
            ob.game.controllers['CNImateFeed'].mode = 'MODULE'
            ob.game.controllers['CNImateFeed'].module = 'animation_delicode_ni_mate_tools.updateFeed'

            ob.game.sensors['SNImateFeed'].link(ob.game.controllers['CNImateFeed'])
            
            if 'NImateFeedImage' not in ob.game.properties:
                bpy.ops.object.game_property_new(type='STRING', name='NImateFeedImage')
            ob.game.properties['NImateFeedImage'].type = 'STRING'
            ob.game.properties['NImateFeedImage'].value = context.scene.delicode_ni_mate_feed_image
            
            if 'NImateUseFeed2' not in ob.game.properties:
                bpy.ops.object.game_property_new(type='BOOL', name='NImateUseFeed2')
            ob.game.properties['NImateUseFeed2'].type = 'BOOL'
            ob.game.properties['NImateUseFeed2'].value = (context.scene.delicode_ni_mate_feed == 'FEED2')

            if 'NImateUseSensor' not in ob.game.properties:
                bpy.ops.object.game_property_new(type='INT', name="NImateUseSensor")
            ob.game.properties['NImateUseSensor'].type = 'INT'
            ob.game.properties['NImateUseSensor'].value = context.scene.delicode_ni_mate_sensor;
 
            return {'FINISHED'}

    class DelicodeNImateReceiverLogicCreate(bpy.types.Operator):
        bl_idname = "wm.delicode_ni_mate_receiver_logic_create"
        bl_label = "Create game logic"
        bl_description = "Create or update game logic for NI mate receiver for the selected object"
        bl_options = {'REGISTER'}

        @classmethod
        def poll(self, context):
            return context.object != None
        
        def execute(self, context):
            ob = context.object

            if 'SNImateReceiver' not in ob.game.sensors:
                bpy.ops.logic.sensor_add(name='SNImateReceiver')
            ob.game.sensors['SNImateReceiver'].use_pulse_true_level = True
            
            if 'CNImateReceiver' not in ob.game.controllers:
                bpy.ops.logic.controller_add(name='CNImateReceiver', type='PYTHON')
            ob.game.controllers['CNImateReceiver'].mode = 'MODULE'
            ob.game.controllers['CNImateReceiver'].module = 'animation_delicode_ni_mate_tools.updateGE'

            ob.game.sensors['SNImateReceiver'].link(ob.game.controllers['CNImateReceiver'])
            
            if 'NImatePort' not in ob.game.properties:
                bpy.ops.object.game_property_new(type='INT', name='NImatePort')
            ob.game.properties['NImatePort'].type = 'INT'
            ob.game.properties['NImatePort'].value = context.scene.delicode_ni_mate_GE_port

            if 'NImateStart' not in ob.game.properties:
                bpy.ops.object.game_property_new(type='BOOL', name='NImateStart')
            ob.game.properties['NImateStart'].type = 'BOOL'
            ob.game.properties['NImateStart'].value = context.scene.delicode_ni_mate_start

            if 'NImateProfile' not in ob.game.properties:
                bpy.ops.object.game_property_new(type='STRING', name='NImateProfile')
            ob.game.properties['NImateProfile'].type = 'STRING'
            ob.game.properties['NImateProfile'].value = context.scene.delicode_ni_mate_start_profile

            if 'NImateQuit' not in ob.game.properties:
                bpy.ops.object.game_property_new(type='BOOL', name='NImateQuit')
            ob.game.properties['NImateQuit'].type = 'BOOL'
            ob.game.properties['NImateQuit'].value = context.scene.delicode_ni_mate_quit

            if 'NImateQuitPort' not in ob.game.properties:
                bpy.ops.object.game_property_new(type='INT', name='NImateQuitPort')
            ob.game.properties['NImateQuitPort'].type = 'INT'
            ob.game.properties['NImateQuitPort'].value = context.scene.delicode_ni_mate_GE_quit_port

            if 'NImateAddRotations' not in ob.game.properties:
                bpy.ops.object.game_property_new(type='BOOL', name='NImateAddRotations')
            ob.game.properties['NImateAddRotations'].type = 'BOOL'
            ob.game.properties['NImateAddRotations'].value = context.scene.delicode_ni_mate_GE_add_rotations
 
            return {'FINISHED'}

    class DelicodeNImate(bpy.types.Operator):
        bl_idname = "wm.delicode_ni_mate_start"
        bl_label = "Delicode NI mate Start"
        bl_description = "Start receiving data from NI mate"
        bl_options = {'REGISTER'}
        
        enabled = False
        receiver = None
        timer = None
        
        def modal(self, context, event):
            if event.type == 'ESC' or not __class__.enabled:
                return self.cancel(context)
            
            if event.type == 'TIMER':
                self.receiver.run(bpy.data.objects, set_location, set_rotation)
            
            return {'PASS_THROUGH'}     

        def execute(self, context):
            __class__.enabled = True
            global add_rotations
            global reset_locrot
            add_rotations = bpy.context.scene.delicode_ni_mate_add_rotations
            reset_locrot = bpy.context.scene.delicode_ni_mate_reset
            self.receiver = NImateReceiver(context.scene.delicode_ni_mate_port, None)
            
            context.window_manager.modal_handler_add(self)
            self.timer = context.window_manager.event_timer_add(1/context.scene.render.fps, context.window)
            return {'RUNNING_MODAL'}
        
        def cancel(self, context):
            __class__.enabled = False
            context.window_manager.event_timer_remove(self.timer)
            
            del self.receiver
            
            return {'CANCELLED'}
        
        @classmethod
        def disable(cls):
            if cls.enabled:
                cls.enabled = False
                
    class DelicodeNImateStop(bpy.types.Operator):
        bl_idname = "wm.delicode_ni_mate_stop"
        bl_label = "Delicode NI mate Stop"
        bl_description = "Stop receiving data from NI mate"
        bl_options = {'REGISTER'}
        
        def execute(self, context):
            DelicodeNImate.disable()
            return {'FINISHED'}
        
    class VIEW3D_PT_DelicodeNImatePanel(bpy.types.Panel):
        bl_space_type = "VIEW_3D"
        bl_region_type = "TOOLS"
        bl_label = "NI mate Receiver"
        bl_category = "NI mate"
        
        def draw(self, context):
            layout = self.layout
            
            scene = context.scene
            
            col = layout.column()
            col.enabled = not DelicodeNImate.enabled
            col.prop(scene, "delicode_ni_mate_port")
            col.label("Create:")
            row = col.row()
            row.prop(scene, "delicode_ni_mate_create", expand=True);
            row = col.row()
            row.prop(scene, "delicode_ni_mate_add_rotations")
            row.prop(scene, "delicode_ni_mate_reset")
            
            if(DelicodeNImate.enabled):
                layout.operator("wm.delicode_ni_mate_stop", text="Stop", icon='ARMATURE_DATA')
            else:
                layout.operator("wm.delicode_ni_mate_start", text="Start", icon='POSE_DATA')

    class VIEW3D_PT_DelicodeNImateGEPanel(bpy.types.Panel):
        bl_space_type = "VIEW_3D"
        bl_region_type = "TOOLS"
        bl_label = "NI mate Game Engine"
        bl_category = "NI mate"
        
        def draw(self, context):
            layout = self.layout

            scene = context.scene

            layout.label("Receiver:")
            layout.prop(scene, "delicode_ni_mate_GE_port")

            row = layout.row(align=True)
            row.prop(scene, "delicode_ni_mate_start", toggle=True)
            col = row.column()
            col.enabled = scene.delicode_ni_mate_start
            col.prop(scene, "delicode_ni_mate_start_profile", text="")

            row = layout.row(align=True)
            row.prop(scene, "delicode_ni_mate_quit", toggle=True)
            col = row.column()
            col.enabled = scene.delicode_ni_mate_quit
            col.prop(scene, "delicode_ni_mate_GE_quit_port", text="Port")

            layout.prop(scene, "delicode_ni_mate_GE_add_rotations")
            col = layout.column()
            if context.object != None and "CNImateReceiver" in context.object.game.controllers:
                col.operator("wm.delicode_ni_mate_receiver_logic_create", icon='FILE_REFRESH', text="Update game logic")
            else:
                col.operator("wm.delicode_ni_mate_receiver_logic_create", icon='GAME')
            
            layout.label("")

            row = layout.row()
            row.label("Sensor:")
            row.prop(scene, "delicode_ni_mate_sensor", expand=True)

            row = layout.row()
            row.label("Live feed:")
            row.prop(scene, "delicode_ni_mate_feed", expand=True)
            layout.operator("wm.delicode_ni_mate_feed_plane_create", icon="TEXTURE")
            layout.prop_search(scene, "delicode_ni_mate_feed_image", bpy.data, "images", text="Or replace")
            col = layout.column()
            if context.object != None and "CNImateFeed" in context.object.game.controllers:
                col.operator("wm.delicode_ni_mate_feed_logic_create", icon='FILE_REFRESH', text="Update game logic")
            else:
                col.operator("wm.delicode_ni_mate_feed_logic_create", icon='GAME')
    
    def init_properties():
        scene = bpy.types.Scene
        
        scene.delicode_ni_mate_port = bpy.props.IntProperty(
            name="Port",
            description="Receive OSC on this port, must match the Full Skeleton port in NI mate!",
            default = 7000,
            min = 0,
            max = 65535)

        scene.delicode_ni_mate_GE_port = bpy.props.IntProperty(
            name="Port",
            description="Receive OSC on this port, must match the Full Skeleton port in NI mate!",
            default = 7000,
            min = 0,
            max = 65535)

        scene.delicode_ni_mate_GE_quit_port = bpy.props.IntProperty(
            name="Quit Port",
            description="NI mate will receive the quit OSC message on this port, must match the OSC input port in NI mate preferences!",
            default = 7000,
            min = 0,
            max = 65535)

        scene.delicode_ni_mate_add_rotations = bpy.props.BoolProperty(
            name="Add Rotations",
            description="Add received rotation data to original rotations")

        scene.delicode_ni_mate_reset = bpy.props.BoolProperty(
            name="Reset",
            description="Reset original object locations and rotations after receiving is stopped",
            default=True)

        scene.delicode_ni_mate_create = bpy.props.EnumProperty(
            name="Create",
            items = [('NONE', 'Nothing', "Don't create objects based on received data"),
                    ('EMPTIES', 'Empties', 'Create empties based on received data'),
                    ('SPHERES', 'Spheres', 'Create spheres based on received data'),
                    ('CUBES', 'Cubes', 'Create cubes based on received data')])

        scene.delicode_ni_mate_feed_image = bpy.props.StringProperty(
            name="Image",
            description="Replace this image with the feed")
        
        scene.delicode_ni_mate_feed = bpy.props.EnumProperty(
            items = [('FEED1', '1', 'Feed 1'), ('FEED2', '2', 'Feed 2')],
            name="Feed")

        scene.delicode_ni_mate_sensor = bpy.props.IntProperty(
            name="Sensor",
            description="Sensor to take the feed from",
            default = 1,
            min = 1,
            max = 10)

        scene.delicode_ni_mate_start = bpy.props.BoolProperty(
            name="Start NI mate",
            description="Start NI mate when the game engine is started")

        scene.delicode_ni_mate_start_profile = bpy.props.StringProperty(
            name="NI mate profile",
            description="Path to the profile file used to start NI mate")

        scene.delicode_ni_mate_quit = bpy.props.BoolProperty(
            name="Quit NI mate",
            description="Quit NI mate when the game engine quits"
            )

        scene.delicode_ni_mate_GE_add_rotations = bpy.props.BoolProperty(
            name="Add Rotations",
            description="Add received rotation data to original rotations")
            
    def clear_properties():
        scene = bpy.types.Scene
        
        del scene.delicode_ni_mate_port
        del scene.delicode_ni_mate_GE_port
        del scene.delicode_ni_mate_GE_quit_port

        del scene.delicode_ni_mate_quit
        del scene.delicode_ni_mate_start

        del scene.delicode_ni_mate_add_rotations
        del scene.delicode_ni_mate_reset
        
        del scene.delicode_ni_mate_GE_add_rotations
        del scene.delicode_ni_mate_create

        del scene.delicode_ni_mate_feed_image
                
    def register():
            
        init_properties()
        bpy.utils.register_module(__name__)

    def unregister():
        bpy.utils.unregister_module(__name__)
        clear_properties()
        
    if __name__ == "__main__":
        register()



def setupGE(own):
    import bge
    import sys

    port = own.get('NImatePort', "")
    global add_rotations
    add_rotations = own.get('NImateAddRotations', False)
    
    if own.get('NImateStart', False):
        profile_path = own.get('NImateProfile', "")
        try:
            if sys.platform.startswith('darwin') or sys.platform.start('Linux'):
                subprocess.call(('open', bge.logic.expandPath(profile_path)))
            elif os.name == 'nt':
                os.startfile(bge.logic.expandPath(profile_path))

            print("Starting NI mate with profile: " + str(profile_path))
        except Exception as e:
            print("Couldn't start NI mate: %s" % e)
            pass

    quit_port = -1

    if own.get('NImateQuit', False):
        quit_port = own.get('NImateQuitPort', -1)

    bge.logic.DelicodeNImate = NImateReceiver(port, quit_port)

def updateGE(controller):
    import bge

    if hasattr(bge.logic, 'DelicodeNImate') == False:
        setupGE(controller.owner)

    bge.logic.DelicodeNImate.run(bge.logic.getCurrentScene().objects, set_GE_location, set_GE_rotation)

def setupFeed(own):
    import bge

    sensor_num = own.get('NImateUseSensor', 1)
    feed_2 = own.get('NImateUseFeed2', False)
    feed_image = own.get('NImateFeedImage', 0)
    
    if isinstance(feed_image, str) == False:
        print("Delicode NI mate Tools Error: no image name defined with String property 'NImateFeedImage'!")
        return None

    return DelicodeNImateFeed("IM" + feed_image, sensor_num, feed_2)

def updateFeed(controller):
    import bge

    own = controller.owner

    sensor_num = own.get('NImateUseSensor', 0)
    feed_2 = own.get('NImateUseFeed2', False)

    if not hasattr(bge.logic, 'DelicodeNImateFeeds'):
        bge.logic.DelicodeNImateFeeds = {}

    if (str(sensor_num*2 + feed_2) not in bge.logic.DelicodeNImateFeeds.keys()) or (bge.logic.DelicodeNImateFeeds[str(sensor_num*2 + feed_2)] == None):
        bge.logic.DelicodeNImateFeeds[str(sensor_num*2 + feed_2)] = setupFeed(own)
    else:
        bge.logic.DelicodeNImateFeeds[str(sensor_num*2 + feed_2)].run()
