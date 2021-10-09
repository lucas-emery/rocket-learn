from typing import List

import numpy as np
import torch
import torch.distributions
from rlgym.gym import Gym
from rlgym.utils.gamestates import GameState
from torch import nn

from rocket_learn.agent.policy import Policy
from rocket_learn.experience_buffer import ExperienceBuffer


def generate_episode(env: Gym, policies: List[Policy]) -> (List[ExperienceBuffer], int):
    """
    create experience buffer data by interacting with the environment(s)
    """
    observations = env.reset()
    done = False

    rollouts = [
        ExperienceBuffer()
        for _ in range(len(policies))
    ]
    ep_rews = [0 for _ in range(len(policies))]
    with torch.no_grad():
        while not done:
            all_indices = []
            all_actions = []

            # if observation isn't a list, make it one so we don't iterate over the observation directly
            if not isinstance(observations, list):
                observations = [observations]

            for policy, obs in zip(policies, observations):
                dist = policy.get_action_distribution(obs)
                action_indices = policy.sample_action(dist, deterministic=False)
                actions = policy.env_compatible(action_indices)

                all_indices.append(action_indices.numpy())
                all_actions.append(actions)

            all_actions = np.array(all_actions)
            old_obs = observations
            observations, rewards, done, info = env.step(all_actions)
            if len(policies) <= 1:
                observations, rewards = [observations], [rewards]
            # Might be different if only one agent?
            for exp_buf, obs, act, rew in zip(rollouts, old_obs, all_indices, rewards):
                exp_buf.add_step(obs, act, rew, done, info)

            for i in range(len(policies)):
                ep_rews[i] += rewards[i]

    result = info["result"]
    # result = 0 if abs(info["state"].ball.position[1]) < BALL_RADIUS else (2 * (info["state"].ball.position[1] > 0) - 1)

    return rollouts, result


def softmax(x):
    """Compute softmax values for each sets of scores in x."""
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum()


class SplitLayer(nn.Module):
    def __init__(self, splits=None):
        super().__init__()
        if splits is not None:
            self.splits = splits
        else:
            self.splits = (3, 3, 3, 3, 3, 2, 2, 2)

    def forward(self, x):
        return torch.split(x, self.splits, dim=-1)


def encode_gamestate(state: GameState):
    state_vals = [0, state.blue_score, state.orange_score]
    state_vals += state.boost_pads.tolist()

    for bd in (state.ball, state.inverted_ball):
        state_vals += bd.position.tolist()
        state_vals += bd.linear_velocity.tolist()
        state_vals += bd.angular_velocity.tolist()

    for p in state.players:
        state_vals += [p.car_id, p.team_num]
        for cd in (p.car_data, p.inverted_car_data):
            state_vals += cd.position.tolist()
            state_vals += cd.quaternion.tolist()
            state_vals += cd.linear_velocity.tolist()
            state_vals += cd.angular_velocity.tolist()
        state_vals += [
            p.match_goals,
            p.match_saves,
            p.match_shots,
            p.match_demolishes,
            p.boost_pickups,
            p.is_demoed,
            p.on_ground,
            p.ball_touched,
            p.has_flip,
            p.boost_amount
        ]
    return state_vals
