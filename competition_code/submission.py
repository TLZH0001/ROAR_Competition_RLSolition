"""
Competition instructions:
Please do not change anything else but fill out the to-do sections.
"""
from stable_baselines3.common.monitor import Monitor
from wandb.integration.sb3 import WandbCallback
from typing import List, Tuple, Dict, Optional
import roar_py_interface
import numpy as np

import roar_py_carla
import roar_py_rl_carla
import gymnasium as gym
from stable_baselines3 import SAC
from roar_py_rl import base_env
import torch as th

import nest_asyncio

def normalize_rad(rad : float):
    return (rad + np.pi) % (2 * np.pi) - np.pi

def filter_waypoints(location : np.ndarray, current_idx: int, waypoints : List[roar_py_interface.RoarPyWaypoint]) -> int:
    def dist_to_waypoint(waypoint : roar_py_interface.RoarPyWaypoint):
        return np.linalg.norm(
            location[:2] - waypoint.location[:2]
        )
    for i in range(current_idx, len(waypoints) + current_idx):
        if dist_to_waypoint(waypoints[i%len(waypoints)]) < 3:
            return i % len(waypoints)
    return current_idx

class SimplifyCarlaActionFilter(gym.ActionWrapper):
    def __init__(self, env: gym.Env):
        super().__init__(env)
        self._action_space = gym.spaces.Dict({
            "throttle": gym.spaces.Box(-1.0, 1.0, (1,), np.float32),
            "steer": gym.spaces.Box(-1.0, 1.0, (1,), np.float32)
        })

class RoarCompetitionSolution:
    def __init__(
        self,
        maneuverable_waypoints: List[roar_py_interface.RoarPyWaypoint],
        vehicle : roar_py_interface.RoarPyActor,
        camera_sensor : roar_py_interface.RoarPyCameraSensor = None,
        location_sensor : roar_py_interface.RoarPyLocationInWorldSensor = None,
        velocity_sensor : roar_py_interface.RoarPyVelocimeterSensor = None,
        rpy_sensor : roar_py_interface.RoarPyRollPitchYawSensor = None,
        occupancy_map_sensor : roar_py_interface.RoarPyOccupancyMapSensor = None,
        collision_sensor : roar_py_interface.RoarPyCollisionSensor = None,
        local_velocimeter_sensor : roar_py_carla.RoarPyCarlaLocalVelocimeterSensor = None,
        gyroscope_sensor : roar_py_carla.RoarPyCarlaGyroscopeSensor = None,
        world : roar_py_carla.RoarPyCarlaWorld = None
    ) -> None:
        self.maneuverable_waypoints = maneuverable_waypoints
        self.vehicle = vehicle
        self.camera_sensor = camera_sensor
        self.location_sensor = location_sensor
        self.velocity_sensor = velocity_sensor
        self.rpy_sensor = rpy_sensor
        self.occupancy_map_sensor = occupancy_map_sensor
        self.collision_sensor = collision_sensor
        self.local_velocimeter_sensor = local_velocimeter_sensor
        self.gyroscope_sensor = gyroscope_sensor
        
        self.world = world
        
        self.env = None
        self.model = None
        self.obs = None


    
    async def initialize(self) -> None:
        self.model = SAC.load("./sample_model", env=None)


        ###### initialize RL environment #############
        nest_asyncio.apply()
        ''' get env '''
        self.env = roar_py_rl_carla.RoarRLCarlaSimEnv(
            self.vehicle,
            self.maneuverable_waypoints,
            self.location_sensor,
            self.rpy_sensor,
            self.local_velocimeter_sensor,
            self.collision_sensor,
            waypoint_information_distances=set([2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 80.0, 100.0]),
            world = self.world,
            collision_threshold = 10.0
        )
        self.env = SimplifyCarlaActionFilter(self.env)
        self.env = gym.wrappers.FilterObservation(self.env, ["gyroscope", "waypoints_information", "local_velocimeter"])
        
        self.env = gym.wrappers.FlattenObservation(self.env)
        self.env = roar_py_rl_carla.FlattenActionWrapper(self.env)
        # self.env = gym.wrappers.RecordEpisodeStatistics(self.env)
        # self.env = gym.wrappers.RecordVideo(self.env, f"videos/competition_eval")
        # self.env = Monitor(self.env, f"logs/competition_eval", allow_early_resets=True)


        ''' get RL model '''
        RUN_FPS= 25
        training_params = dict(
            learning_rate = 1e-5,  # be smaller 2.5e-4
            #n_steps = 256 * RUN_FPS, #1024
            batch_size=256,  # mini_batch_size = 256?
            # n_epochs=10,
            gamma=0.97,  # rec range .9 - .99 0.999997
            ent_coef="auto",
            target_entropy=-10.0,
            # gae_lambda=0.95,
            # clip_range_vf=None,
            # vf_coef=0.5,
            # max_grad_norm=0.5,
            use_sde=True,
            sde_sample_freq=RUN_FPS * 2,
            # target_kl=None,
            # tensorboard_log=(Path(misc_params["model_directory"]) / "tensorboard").as_posix(),
            # create_eval_env=False,
            # policy_kwargs=None,
            verbose=1,
            seed=1,
            device=th.device('cuda' if th.cuda.is_available() else 'cpu'),
            # _init_setup_model=True,
        )
        model_path = "sample_model"
        self.model = SAC.load(
            model_path,
            env=self.env, 
            **training_params
        )

        ''' reset env '''
        self.obs, info = self.env.reset()



    async def step(
        self
    ) -> None:
        """
        This function is called every world step.
        Note: You should not call receive_observation() on any sensor here, instead use get_last_observation() to get the last received observation.
        You can do whatever you want here, including apply_action() to the vehicle.
        """
        # TODO: Implement your solution here.

        ''' get action '''
        action, _state = self.model.predict(self.obs, deterministic=False)
        # print('ACTION:', action)
        self.obs, reward, terminated, truncated, info = self.env.step(action) # this statement causes error
        return action


        # # Receive location, rotation and velocity data 
        # vehicle_location = self.location_sensor.get_last_gym_observation()
        # vehicle_rotation = self.rpy_sensor.get_last_gym_observation()
        # vehicle_velocity = self.velocity_sensor.get_last_gym_observation()
        # vehicle_velocity_norm = np.linalg.norm(vehicle_velocity)
        
        # # Find the waypoint closest to the vehicle
        # self.current_waypoint_idx = filter_waypoints(
        #     vehicle_location,
        #     self.current_waypoint_idx,
        #     self.maneuverable_waypoints
        # )
        #  # We use the 3rd waypoint ahead of the current waypoint as the target waypoint
        # waypoint_to_follow = self.maneuverable_waypoints[(self.current_waypoint_idx + 3) % len(self.maneuverable_waypoints)]

        # # Calculate delta vector towards the target waypoint
        # vector_to_waypoint = (waypoint_to_follow.location - vehicle_location)[:2]
        # heading_to_waypoint = np.arctan2(vector_to_waypoint[1],vector_to_waypoint[0])

        # # Calculate delta angle towards the target waypoint
        # delta_heading = normalize_rad(heading_to_waypoint - vehicle_rotation[2])

        # # Proportional controller to steer the vehicle towards the target waypoint
        # steer_control = (
        #     -8.0 / np.sqrt(vehicle_velocity_norm) * delta_heading / np.pi
        # ) if vehicle_velocity_norm > 1e-2 else -np.sign(delta_heading)
        # steer_control = np.clip(steer_control, -1.0, 1.0)

        # # Proportional controller to control the vehicle's speed towards 40 m/s
        # throttle_control = 0.05 * (20 - vehicle_velocity_norm)

        # control = {
        #     "throttle": np.clip(throttle_control, 0.0, 1.0),
        #     "steer": steer_control,
        #     "brake": np.clip(-throttle_control, 0.0, 1.0),
        #     "hand_brake": 0.0,
        #     "reverse": 0,
        #     "target_gear": 0
        # }
        # await self.vehicle.apply_action(control)
        # return control