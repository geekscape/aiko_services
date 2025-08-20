#!/usr/bin/env python
#
# Create a virtual world using the Panda3D physics engine.
# The virtual world creates an Aiko Services Pipeline and
# provides various DataSources, e.g a stream of images.
#
# Usage
# ~~~~~
# pview models/robot.egg.pz models/robot-run.egg.pz
# pview models/robot.egg.pz models/robot-walk.egg.pz
# pview models/world.egg.pz
# punzip models/world.egg.pz -o models/world.egg
#
# ./world.py  [--help]
#     [--collision_mask 4]
#     [--definition_pathname pathname]
#     [--frame_rate_pipeline 4]
#     [--frame_rate_world 10]
#     [--graph_path name]
#     [--log_level error|warning|info|debug]
#     [--log_mqtt all|false|true]
#     [--name pipeline_name]
#     [--stream_id "{}"]
#
# ./world.py -gp World      -ll debug
# ./world.py -gp World_OODA -ll debug
#
# Usage over the network
# ~~~~~~~~~~~~~~~~~~~~~~
# aiko_pipeline create ../../../elements/media/webcam_zmq_pipeline_0.json  \
#               -s 1 -p resolution 640x480  # produce images, like "world.py"
#
# ./world.py -gp World_ZMQ  -ll debug -dt zmq://192.168.0.1:6502
#
# aiko_pipeline create world_pipeline.json    -s 1 -ll debug -gp ZMQ_OODA
#
# aiko_pipeline create ../robot_pipeline.json -s 1 -ll debug
#
# Attribution
# ~~~~~~~~~~~
# Origin:  https://github.com/panda3d/panda3d/tree/master/samples/roaming-ralph
# License: Modified BSD: http://www.opensource.org/licenses/bsd-license.php
# Author:  Ryan Myers
# Models:  Jeff Styers, Reagan Heller
# Last Updated: 2015-03-13
#
# Provides an example of creating a character and having it walk around
# on uneven terrain, as well as implementing a fully rotatable camera
#
# To Do
# ~~~~~
# - Insert some "image.jpg" into the "models/world.egg.pz" !
#   - Astra, XGo-Mini 2
#   - 2001 Monolith, De Lorean, Dinosaur (chasing ?), Iron Giant, R2-D2
# - Investigate collision handling for these added objects
#
# - Provide robot HUD (toggle-able)
#   - Also provide robot variables via Eventual Consistency "self.shared[]"
# - Provide top-down navigation mini-map with robot tracks (toggle-able)
#
# * Panda3D NodePath for each Aiko Services Actor / Pipeline / PipelineElement
#   - Aiko Services 3D GUI
#     - See https://docs.panda3d.org/1.10/python/more-resources/cheat-sheets
#
# - Implement robot action / command functions (tool calling)
#   - Use Pipeline "queue_response"
#
# - World images should be the robot POV, not the camera POV !
#   - See "camera_tracking_toggle()"
#
# - Improve help instructions
# - FIX: Camera roll (y-axis) doesn't work :(
# - Extend keyboard control of camera and robot
#
# - World should provide Interface for ...
#   - DataSources(PipelineElement) and DataTargets(PipelineElement)
#     - DataSources: audio, LIDAR, telemetry (status), video
#     - DataTargets: audio, telemetry (control)
#
# - Investigate https://docs.panda3d.org/1.10/python/reference/panda3d.ai
#   - AIBehaviors, AICharacter, AINode, AIWorld, Flock

import click
import math
import numpy as np
import os
from PIL import Image
import random
import sys
from threading import Thread
from typing import Tuple

from direct.actor.Actor import Actor
from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    AmbientLight, Camera, CardMaker, ClockObject,
    CollideMask, CollisionNode, CollisionHandlerPusher, CollisionHandlerQueue,
    CollisionRay, CollisionSphere, CollisionTraverser,
    DirectionalLight, DisplayRegion, LColor,
    NodePath, PandaNode, TextNode, Texture
)

import aiko_services as aiko
from aiko_services.main.utilities import get_pid

_COLLISION_MASK = 0b000
_DEFINITION_PATHNAME = "world_pipeline.json"
_FRAME_RATE = 20  # Pipeline and PhysicsEngine World frames per second
_GRACE_TIME = 5   # seconds
_PIPELINE_NAME = "p_world"
_VERSION = 0

# --------------------------------------------------------------------------- #

class PhysicsEngine(ShowBase):
    def __init__(self, collision_mask=_COLLISION_MASK, frame_rate=_FRAME_RATE):
        ShowBase.__init__(self)

        globalClock.setMode(ClockObject.MLimited)  # noqa: F821
        globalClock.setFrameRate(frame_rate)       # noqa: F821

        self.collision_mask = collision_mask
        self.environment = self.create_environment()
        self.robot, self.hover = self.create_robot()

        self.image = None     # for World(DataSource)
        self.image_count = 0  # for World(DataSource)

        self.items = [        # TODO: random items everywhere
            self.create_item("box",    (1, 0, 0, 1), ( 3, -10, 0)),
            self.create_item("sphere", (0, 1, 0, 1), ( 0, -10, 0)),
            self.create_item("box",    (0, 0, 1, 1), (-3, -10, 0))
        ]

        self.disable_mouse()  # disable default camera movement
        self.reset_camera()
        self.create_minimap((0.8, 1.0, 0.8, 1.0))

        self.add_instructions()
        self.key_map = self.create_keyboard_mapping()

        self.create_collision_handlers()  # TODO: refactor into "create_robot()"

        taskMgr.add(self.update_camera, "task_update_camera")  # noqa: F821
        taskMgr.add(self.update_items,  "task_update_items")   # noqa: F821
        taskMgr.add(self.update_robot,  "task_update_robot")   # noqa: F821

    def add_instruction(self, position, message):
        return OnscreenText(
            text=message, style=1, fg=(1, 1, 1, 1), scale=.05,
            shadow=(0, 0, 0, 1), parent=base.a2dTopLeft,         # noqa: F821
            pos=(0.08, -position - 0.04), align=TextNode.ALeft)

    def add_instructions(self):
        self.title = self.add_title("Aiko Services virtual world")
        self.inst3 = self.add_instruction(0.06, "Arrow ^  Run Forward")    # ↑
        self.inst4 = self.add_instruction(0.12, "Arrow v  Walk Backward")  # ↓
        self.inst1 = self.add_instruction(0.18, "Arrow <  Rotate Left")    # ←
        self.inst2 = self.add_instruction(0.24, "Arrow >  Rotate Right")   # →
        gap = " "*13
        self.inst5 = self.add_instruction(0.30, f"a {gap} Camera Yaw Left")
        self.inst6 = self.add_instruction(0.36, f"d {gap} Camera Yaw Right")
        self.inst7 = self.add_instruction(0.42, f"x {gap} Exit")

    def add_title(self, text):
        return OnscreenText(
            parent=base.a2dBottomRight, align=TextNode.ARight,  # noqa: F821
            text=text, style=1,
            fg=(1.0, 1.0, 1.0, 1.0), bg=(0.3, 0.3, 0.3, 0.8),
            scale=0.05, pos=(-0.1, 0.09), shadow=(0.0, 0.0, 0.0, 1.0))

    def camera_tracking_toggle(self):
        self.camera_tracking = not self.camera_tracking

    def create_collision_handlers(self):  # TODO: refactor into "create_robot()"
    # https://docs.panda3d.org/1.10/python/reference/direct.showbase.ShowBase#direct.showbase.ShowBase.ShowBase.cTrav
        self.cTrav = CollisionTraverser()  # must be named "self.cTrav"
        collision_traverser = self.cTrav

    # Robot is composed of two spheres
    # One around the torso and one around the head
    # Slightly oversized so that the robot keeps some distance from obstacles
    #
    # Use CollisionHandlerPusher to handle collisions between robot and
    # the environment.  Robot is added as a "from" object which will be
    # "pushed" out of the environment when walking into obstacles

        collision_node = CollisionNode("robot")
        collision_node.add_solid(CollisionSphere(
            center=(0, 0, 2), radius=1.5))
        collision_node.add_solid(CollisionSphere(
            center=(0, -0.25, 4), radius=1.5))
        collision_node.set_from_collide_mask(CollideMask.bit(0))
        collision_node.set_into_collide_mask(CollideMask.all_off())

        robot_collision_node = self.robot.attach_new_node(collision_node)

        handler_pusher = CollisionHandlerPusher()
        handler_pusher.horizontal = True

    # Need to add robot to both the pusher and the traverser
    # Pusher needs to know which node to push back when a collision occurs

        handler_pusher.add_collider(robot_collision_node, self.robot)
        collision_traverser.add_collider(
            robot_collision_node, handler_pusher)

    # Detect the height of the terrain by creating a collision ray
    # and casting it downward toward the terrain.
    # One ray starts above robot's head and the other starts above the camera.
    # A collision ray may hit the terrain or it may hit a rock or a tree.
    # If it hits the terrain, we can detect the terrain height

        self.robot_collision_handler_queue = CollisionHandlerQueue()
        robot_ground_ray = CollisionRay()
        robot_ground_ray.set_origin(0, 0, 9)
        robot_ground_ray.set_direction(0, 0, -1)
        robot_ground_collision = CollisionNode("robot_ground_ray")
        robot_ground_collision.add_solid(robot_ground_ray)
        robot_ground_collision.set_from_collide_mask(CollideMask.bit(0))
        robot_ground_collision.set_into_collide_mask(CollideMask.all_off())

        robot_ground_collision_node = self.robot.attach_new_node(
            robot_ground_collision)

        collision_traverser.add_collider(
            robot_ground_collision_node, self.robot_collision_handler_queue)

        camera_ground_ray = CollisionRay()
        camera_ground_ray.setOrigin(0, 0, 9)
        camera_ground_ray.setDirection(0, 0, -1)
        self.camGroundCol = CollisionNode("camRay")
        self.camGroundCol.addSolid(camera_ground_ray)
        self.camGroundCol.setFromCollideMask(CollideMask.bit(0))
        self.camGroundCol.setIntoCollideMask(CollideMask.allOff())
        self.camGroundColNp = self.camera.attachNewNode(self.camGroundCol)
        self.camGroundHandler = CollisionHandlerQueue()
        collision_traverser.addCollider(
            self.camGroundColNp, self.camGroundHandler)

        if self.collision_mask & 0b001:
            robot_collision_node.show()
        if self.collision_mask & 0b010:
            self.camGroundColNp.show()
        if self.collision_mask & 0b100:
            collision_traverser.showCollisions(self.render)

    # This environment model contains collision meshes.
    # If you look in the egg file, you will see the following ...
    #     <Collide> { Polyset keep descend }
    # This tag causes the following mesh to be converted to a collision
    # mesh ... a mesh which is optimized for collision, not rendering.
    # It also keeps the original mesh, so there are now two copies,
    # one optimized for rendering, one for collisions

    def create_environment(self):
    # Don't have a skybox ... use sky blue background color instead
        self.set_background_color(0.53, 0.80, 0.92, 1)

        environment = loader.loadModel("models/world")  # noqa: F821
        environment.reparentTo(self.render)
        return environment

    def create_keyboard_mapping(self):
        keyboard_mapping = {
            "left":              0,
            "right":             0,
            "forward":           0,
            "backward":          0,

            "camera-left":       0,  # - x-axis translation
            "camera-right":      0,  # + x-axis translation
            "camera-backward":   0,  # - y-axis translation
            "camera-forward":    0,  # + y-axis translation
            "camera-down":       0,  # - z-axis translation
            "camera-up":         0,  # + z-axis translation

            "camera-pitch-down": 0,  # - x-axis rotation
            "camera-pitch-up":   0,  # + x-axis rotation
            "camera-roll-left":  0,  # - y-axis rotation
            "camera-roll-right": 0,  # + y-axis rotation
            "camera-yaw-left":   0,  # - z-axis rotation
            "camera-yaw-right":  0   # + z-axis rotation
        }

    # https://docs.panda3d.org/1.10/python/programming/hardware-support/keyboard-support
    #   sa = "shift-arrow"  # also "alt", "control" and "meta" key modifiers
    #   self.accept(f"{sa}_left",    self.do_key, ["camera-roll-left",  True])
    #   self.accept(f"{sa}_right",   self.do_key, ["camera-roll-right", True])
    # "arrow_<direction>-up" and "<modifier>-arrow_<direction>-up" :(
    #   self.accept("arrow_left-up",  self.do_key, ["arrow_cancel", False])
    #   self.accept("arrow_right-up", self.do_key, ["arrow_cancel", False])

        self.accept("arrow_down",     self.do_key, ["backward", True])
        self.accept("arrow_down-up",  self.do_key, ["backward", False])
        self.accept("arrow_up",       self.do_key, ["forward",  True])
        self.accept("arrow_up-up",    self.do_key, ["forward",  False])
        self.accept("arrow_left",     self.do_key, ["left",     True])
        self.accept("arrow_left-up",  self.do_key, ["left",     False])
        self.accept("arrow_right",    self.do_key, ["right",    True])
        self.accept("arrow_right-up", self.do_key, ["right",    False])

        self.accept("a",              self.do_key, ["camera-left",     True])
        self.accept("a-up",           self.do_key, ["camera-left",     False])
        self.accept("d",              self.do_key, ["camera-right",    True])
        self.accept("d-up",           self.do_key, ["camera-right",    False])
        self.accept("s",              self.do_key, ["camera-backward", True])
        self.accept("s-up",           self.do_key, ["camera-backward", False])
        self.accept("w",              self.do_key, ["camera-forward",  True])
        self.accept("w-up",           self.do_key, ["camera-forward",  False])
        self.accept("q",              self.do_key, ["camera-down",     True])
        self.accept("q-up",           self.do_key, ["camera-down",     False])
        self.accept("z",              self.do_key, ["camera-up",       True])
        self.accept("z-up",           self.do_key, ["camera-up",       False])

        self.accept("k",             self.do_key, ["camera-pitch-down", True])
        self.accept("k-up",          self.do_key, ["camera-pitch-down", False])
        self.accept("i",             self.do_key, ["camera-pitch-up",   True])
        self.accept("i-up",          self.do_key, ["camera-pitch-up",   False])
        self.accept("u",             self.do_key, ["camera-roll-left",  True])
        self.accept("u-up",          self.do_key, ["camera-roll-left",  False])
        self.accept("m",             self.do_key, ["camera-roll-right", True])
        self.accept("m-up",          self.do_key, ["camera-roll-right", False])
        self.accept("j",             self.do_key, ["camera-yaw-left",   True])
        self.accept("j-up",          self.do_key, ["camera-yaw-left",   False])
        self.accept("l",             self.do_key, ["camera-yaw-right",  True])
        self.accept("l-up",          self.do_key, ["camera-yaw-right",  False])

    # TODO: Round-robin through modes ?
        self.accept("0", self.render.clear_render_mode)          # default
        self.accept("1", self.render.set_render_mode_wireframe)
        self.accept("2", self.render.hide_bounds)                # default
        self.accept("3", self.render.show_bounds)

        self.accept("shift-c", self.reset_camera)
        self.accept("shift-e", self.messenger.toggleVerbose)  # show events
        self.accept("shift-k", self.print_keyboard_map)
    #   self.accept("shift-m", self.render.set_render_mode_wireframe)
        self.accept("shift-o", self.oobe)                     # visual diagnosis
        self.accept("shift-r", self.reset_robot)
        self.accept("t", self.camera_tracking_toggle)
        self.accept("x", sys.exit)

        return keyboard_mapping

    def create_item(self,
            shape="box", color=(1.0, 0.0, 0.0, 1.0), position=(0, -10, 0)):

        shape = "smiley" if shape == "sphere" else shape
        position = self.robot.get_pos() + position

        item = self.loader.loadModel(f"models/{shape}")
        item.set_color(color)
        item.set_pos(position)
        item.set_scale(1, 1, 1)
        item.reparent_to(self.render)
        return item

    def create_lights(self):
        ambient_light = AmbientLight("ambient_light")
        ambient_light.set_color((0.3, 0.3, 0.3, 1))
        ambient_light = self.render.attach_new_node(ambient_light)
        self.render.set_light(ambient_light)

        directional_light = DirectionalLight("directional_light")
        directional_light.set_color((1, 1, 1, 1))
        directional_light.set_direction((-5, -5, -5))
    #   directional_light.set_hpr(0, -45, 0)  # set light direction
        directional_light.set_specular_color((1, 1, 1, 1))
        directional_light = self.render.attach_new_node(directional_light)
        self.render.set_light(directional_light)

# https://docs.panda3d.org/1.10/python/programming/rendering-process/display-regions

    def create_minimap(self, region):
        if not isinstance(region, tuple) or len(region) != 4:
            raise ValueError("Region must be a tuple of four floats")

        card_maker = CardMaker("minimap_background")
        card_maker.set_frame(region[0], region[1], region[2], region[3])
        background = NodePath(card_maker.generate())
        background.set_color(LColor(1.0, 1.0, 1.0, 1))  # white
        background.set_transparency(False)
        background.reparent_to(self.aspect2d)

        camera_lens = self.camLens.make_copy()
        camera_lens.set_fov(45)
        camera_lens.set_near_far(1, 1000)

        camera = Camera("camera", camera_lens)
        camera_node_path = NodePath(camera)
        camera_node_path.set_pos(0, 0, 500)
        camera_node_path.look_at(0, 0, 0)
        camera_node_path.reparent_to(self.hover)

        display_region = self.win.make_display_region(*region)
        display_region.sort = 10
        display_region.camera = camera_node_path

    #   card_maker = CardMaker("minimap_border")
    #   card_maker.set_frame(
    #       region[0] - 0.1, region[1] + 0.1, region[2] - 0.1, region[3] + 0.1)
    #   border = NodePath(card_maker.generate())
    #   border.set_color(LColor(1.0, 1.0, 0.0, 1.0))  # yellow
    #   border.set_transparency(True)
    #   border.reparent_to(self.aspect2d)

    def create_robot(self):
        self.robot = Actor("models/robot", {
                         "run":  "models/robot-run",
                         "walk": "models/robot-walk"})
        self.reset_robot()
        self.robot.reparentTo(self.render)

    # Create "hover" floating just above the robot, used as camera target
        hover = NodePath(PandaNode("hover"))
        hover.set_z(2.0)
        hover.reparentTo(self.robot)

        return self.robot, hover

    def do_key(self, key, value):
    # "arrow_<direction>-up" and "<modifier>-arrow_<direction>-up" :(
        if key == "arrow_cancel":
            self.key_map["camera-roll-left"]  = False
            self.key_map["camera-roll-right"] = False
            self.key_map["camera-yaw-left"]   = False
            self.key_map["camera-yaw-right"]  = False
        else:
            self.key_map[key] = value

    def print_keyboard_map(self):
        print(self.win.get_keyboard_map())

    def reset_camera(self):
        self.camera_direction = (0.0, 0.0, 0.0)
        self.camera_delta = 2.0
        self.camera_tracking = True

        self.camera.set_pos(self.robot.get_x(), self.robot.get_y() + 10, 2.0)

    def reset_robot(self):
        start_position = self.environment.find("**/start_point").get_pos()
        self.robot.set_pos(start_position + (0.0, 0.0, 1.5))
        self.robot.set_scale(0.2)

    def update_camera(self, task):
        camera = self.camera
        dt = base.clock.dt  # noqa: F821

        if self.key_map["camera-left"]:
            camera.set_x(camera, -20 * dt)
        if self.key_map["camera-right"]:
            camera.set_x(camera,  20 * dt)

    # Keep camera within a reasonable distance of the robot
        vector = self.robot.get_pos() - camera.get_pos()
        vector.set_z(0)
        distance = vector.length()
        vector.normalize()
        if distance < 5.0:   # too close
            camera.set_pos(camera.get_pos() - vector * (5.0 - distance))
        if distance > 10.0:  # too far
            camera.set_pos(camera.get_pos() + vector * (distance - 10.0))

    # Keep camera above the terrian and above the robot
        entries = list(self.camGroundHandler.entries)
        entries.sort(
            key=lambda x: x.getSurfacePoint(render).get_z())  # noqa: F821

        for entry in entries:
            if entry.get_into_node().name == "terrain":
                camera.set_z(
                    entry.getSurfacePoint(render).get_z() + 1.5)  # noqa: F821
        if camera.get_z() < self.robot.get_z() + 2.0:
            camera.set_z(self.robot.get_z() + 2.0)

    # Look in robot's direction and not facing downwards (use robot's hover)
        camera.lookAt(self.hover)

        return task.cont

    def update_items(self, task):
        for item in self.items:
            item.set_hpr(task.time * 90, task.time * 90, 0)
        return task.cont

    def update_robot(self, task):
        dt = base.clock.dt  # noqa: F821
        robot = self.robot

        if self.key_map["left"]:
            robot.set_h(robot.get_h() + 300 * dt)
        if self.key_map["right"]:
            robot.set_h(robot.get_h() - 300 * dt)
        if self.key_map["forward"]:
            robot.set_y(robot, -20 * dt)
        if self.key_map["backward"]:
            robot.set_y(robot,  10 * dt)

        # If robot is moving, then loop animation, else stop animation

        current_anim = robot.get_current_anim()
        if self.key_map["forward"]:
            if current_anim != "run":
                robot.loop("run")
        elif self.key_map["backward"]:
            if current_anim != "walk":
                robot.loop("walk")
            robot.set_play_rate(-1.0, "walk")  # play walk animation backwards
        elif self.key_map["left"] or self.key_map["right"]:
            if current_anim != "walk":
                robot.loop("walk")
            robot.set_play_rate(1.0, "walk")
        else:
            if current_anim is not None:
                robot.stop()
                robot.pose("walk", 5)
                self.is_moving = False

    # Normally, we would have to call traverse() to check for collisions.
    # However, the class ShowBase that we inherit from has a task to do
    # this for us, if we assign a CollisionTraverser to collision_traverser

        # collision_traverser(render)  # see self.create_collision_handlers

    # Adjust robot's Z coordinate.  If robot's ray hit terrain, update robot Z

        entries = list(self.robot_collision_handler_queue.entries)
        entries.sort(
            key=lambda x: x.get_surface_point(render).get_z())  # noqa: F821

        for entry in entries:
            if entry.get_into_node().name == "terrain":
                robot.set_z(
                    entry.get_surface_point(render).get_z())  # noqa: F821

    # Convert rendered frame to an image for the World

        texture = self.win.get_screenshot()  # panda3d.core.Texture
        if texture and texture.has_ram_image():
            data = texture.get_ram_image_as("RGBA").get_data()
            resolution = (texture.get_x_size(), texture.get_y_size())
            rgba_image = Image.frombytes("RGBA", resolution, data)
            rgb_image = rgba_image.convert("RGB")
            rgb_image = rgb_image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            self.image = np.array(rgb_image)
            self.image_count += 1

        return task.cont

# --------------------------------------------------------------------------- #
# physics_engine --> PhysicsEngine(direct.showbase.ShowBase)
# physics_engine.win --> panda3d.core.GraphicsWindow
# physics_engine.win.get_screenshot() --> panda3d.core.Texture
# physics_engine.win.save_screenshot(image_pathname) --> boolean
#
# pnm_image = PNMImage()
# physics_engine.win.get_screenshot(pnm_image)
#
# panda3d.core.PNMImage  # 2D Texture
# - https://docs.panda3d.org/1.10/python/programming/texturing
# - https://docs.panda3d.org/1.10/python/reference/panda3d.core.PNMImage
# - https://docs.panda3d.org/1.10/python/programming/texturing/creating-textures
#
# panda3d.core.Texture
# - https://docs.panda3d.org/1.10/python/reference/panda3d.core.Texture

class World(aiko.PipelineElement):  # TODO: Should be a DataSource
    def __init__(self, context):
        context.set_protocol("device:0")
        context.call_init(self, "PipelineElement", context)
        self.share["source_file"] = f"v{_VERSION}⇒ {__file__}"

    def start_stream(self, stream, stream_id):
        rate, _ = self.get_parameter("rate", default=_FRAME_RATE)
        self.create_frames(stream, self.frame_generator, rate=float(rate))
        return aiko.StreamEvent.OKAY, {}

    def frame_generator(self, stream, frame_id):
        return aiko.StreamEvent.OKAY, {"data": None}

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        physics_engine = stream.parameters["physics_engine"]
    #   graphics_engine = physics_engine.graphics_engine
    #   graphics_window = physics_engine.win
    #   task_manager = physics_engine.task_mgr

        image = physics_engine.image
        if image is not None:
        #   count = physics_engine.image_count
        #   self.logger.debug(f"{self.my_id()}: image {count}")
            return aiko.StreamEvent.OKAY, {"images": [image]}
        return aiko.StreamEvent.OKAY, {"images": []}

@click.command("main", help="Create World Pipeline")
@click.option("--collision_mask", "-cm", type=int,
    default=_COLLISION_MASK, required=False,
    help="Show various collision diagnostics (bits 0, 1, 2)")
@click.option("--data_targets", "-dt", type=str,
    default=None, required=False,
    help="ML Pipeline URL: zmq://host:port, e.g zmq://192.168.0.1:6502")
@click.option("--definition_pathname", "-dp", type=str,
    default=_DEFINITION_PATHNAME, required=False,
    help="Pipeline name")
@click.option("--frame_rate_pipeline", "-frp", type=float,
    default=_FRAME_RATE, required=False,
    help="Machine Learning Pipeline frame rate")
@click.option("--frame_rate_world", "-frw", type=float,
    default=_FRAME_RATE, required=False,
    help="PhysicsEngine World frame rate")
@click.option("--graph_path", "-gp", type=str,
    default=None, required=False,
    help="Pipeline Graph Path, use Head_PipelineElement_name")
@click.option("--log_level", "-ll", type=str,
    default="INFO", required=False,
    help="error, warning, info, debug")
@click.option("--log_mqtt", "-lm", type=str,
    default="all", required=False,
    help="all, false (console), true (mqtt)")
@click.option("--name", "-n", type=str,
    default=_PIPELINE_NAME, required=False,
    help="Pipeline name")
@click.option("--stream_id", "-s", type=str,
    default="1", required=False,
    help='Create Stream with identifier with optional process_id "name_{}"')

def main(collision_mask, data_targets, definition_pathname,
         frame_rate_pipeline, frame_rate_world, graph_path,
         log_level, log_mqtt, name, stream_id):

    os.environ["AIKO_LOG_LEVEL"] = log_level.upper()
    os.environ["AIKO_LOG_MQTT"] = log_mqtt

    physics_engine = PhysicsEngine(
        collision_mask=collision_mask, frame_rate=frame_rate_world)

    if stream_id:
        stream_id = stream_id.replace("{}", get_pid())  # sort-of unique id

    parameters = {
        "physics_engine": physics_engine,
        "rate": frame_rate_pipeline
    }
    if data_targets:
        parameters["ImageWriteZMQ.data_targets"] = data_targets

    pipeline_definition = aiko.PipelineImpl.parse_pipeline_definition(
        definition_pathname)
    pipeline = aiko.PipelineImpl.create_pipeline(
        definition_pathname, pipeline_definition, name, graph_path, stream_id,
        parameters=parameters, frame_id=0, frame_data=None,
        grace_time=_GRACE_TIME, queue_response=None, stream_reset=False)
    Thread(target=pipeline.run, daemon=True).start()

    physics_engine.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
