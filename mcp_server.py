"""Expose the example Python operations through a local stdio MCP server.

The coding agent launches this file. Its stdout is reserved for the MCP protocol
"""

import argparse
from contextlib import redirect_stdout
import os
from pathlib import Path
import sys
from threading import Lock
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import StrictFloat, StrictInt

with redirect_stdout(sys.stderr):
    from sizing_tools import SizingExperiment


def create_server(experiment):
    """Register tools for one experiment; serialize calls that share its state."""
    server = MCPServer(
        "CAD sizing",
        description="Circuit simulation, random warmup, TD3 training, and experiment status.",
    )
    lock = Lock()

    def call(method, **arguments):
        with lock, redirect_stdout(sys.stderr):
            try:
                return getattr(experiment, method)(**arguments)
            except (ValueError, RuntimeError) as error:
                raise ToolError(str(error)) from error

    @server.tool()
    def simulate(parameters: dict[str, StrictFloat]) -> dict[str, Any]:
        """Simulate a complete physical design on the YAML parameter grids.

        Supply all 20 named parameters: multiplicities are counts, widths/lengths
        are meters, cap is farads, and res is ohms. Invalid values are rejected.
        Return actual parameters, physical/normalized specs, units, reward, and
        hard_constraints_satisfied. Record the design without changing RL replay,
        weights, or the current episode. Uses one simulator call.
        Specs: area m^2, current A, gain V/V, noise V RMS, phm degrees,
        slewRate rising 10-90% V/us, and ugbw Hz. Higher reward is better.
        """
        return call("simulate", parameters=parameters)

    @server.tool()
    def warmup(n_steps: StrictInt) -> dict[str, Any]:
        """Add n_steps random RL transitions (1..1000), without updating weights.

        Continue the shared buffer and episode. Return status, best candidates,
        experiences_added, simulator_calls_used, and updates_performed (zero).
        Episode resets use additional simulations. Prefer small batches.
        """
        return call("warmup", n_steps=n_steps)

    @server.tool()
    def train(n_steps: StrictInt) -> dict[str, Any]:
        """Continue TD3 for n_steps new environment transitions (1..1000).

        Require warmup to fill at least batch_size experiences (default 100).
        Append new experiences and learn from the shared replay buffer. Actor
        updates follow TD3's delay. Return progress, per-call counts, and best
        candidates by reward. Resets cost extra simulations. Prefer small batches.
        """
        return call("train", n_steps=n_steps)

    @server.tool()
    def get_status(k: StrictInt = 5) -> dict[str, Any]:
        """Read counters and the k best distinct measured candidates (1..20).

        Includes physical parameters, specs, normalized specs, reward and constraint
        satisfaction. simulator_calls counts attempts, including resets and failures.
        Does not simulate or train. Candidates may be infeasible; inspect their flag.
        """
        return call("get_status", k=k)

    return server


def main():
    parser = argparse.ArgumentParser(description="CAD sizing MCP server (stdio)")
    parser.add_argument("--seed", type=int, default=123456)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--replay-size", type=int, default=100_000)
    args = parser.parse_args()
    # Existing course code resolves model/netlist paths relative to the project.
    os.chdir(Path(__file__).resolve().parent)
    with redirect_stdout(sys.stderr):
        experiment = SizingExperiment(args.seed, args.batch_size, args.replay_size)
    create_server(experiment).run(transport="stdio")


if __name__ == "__main__":
    main()
