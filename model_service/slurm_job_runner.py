#!/usr/bin/env python3
"""Module for SLUM jobs"""
import argparse
import pathlib
import subprocess


def main():
    """Sequence of steps to submit a SLURM job for a particular ML model"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--action",
        required=True,
        type=str,
        help="Action for job runner to perform",
    )
    parser.add_argument(
        "--model_instance_id",
        required=True,
        type=str,
        help="Model type not supported",
    )
    parser.add_argument("--model_type", type=str, help="Type of model requested")
    parser.add_argument("--model_path", type=str, help="Model type not supported")
    parser.add_argument("--gateway_host", type=str, help="Hostname of gateway service")
    parser.add_argument("--gateway_port", type=int, help="Port of gateway service")
    args = parser.parse_args()

    cwd = pathlib.Path(__file__).parent.resolve()

    if args.action == "launch":
        if not args.model_type:
            print("Argument --model_type must be specified to launch a job")
            return
        if not args.model_path:
            print("Argument --model_path must be specified to launch a job")
            return
        if not args.gateway_host:
            print("Argument --gateway_host must be specified to launch a job")
            return
        if not args.gateway_port:
            print("Argument --gateway_port must be specified to launch a job")
            return

        try:
            if args.model_type == "OPT-175B":
                scheduler_cmd = f"sbatch --job-name={args.model_instance_id} \
                {cwd}/slurm/OPT-175B_service.sh {cwd} {args.gateway_host} {args.gateway_port}"
                print(f"Scheduler command: {scheduler_cmd}")
                scheduler_output = subprocess.check_output(scheduler_cmd, shell=True).decode(
                    "utf-8"
                )
                print(f"{scheduler_output}")
            elif args.model_type == "OPT-6.7B":
                scheduler_cmd = f"sbatch --job-name={args.model_instance_id} \
                {cwd}/slurm/OPT-6.7B_service.sh {cwd} {args.gateway_host} {args.gateway_port}"
                print(f"Scheduler command: {scheduler_cmd}")
                scheduler_output = subprocess.check_output(scheduler_cmd, shell=True).decode(
                    "utf-8"
                )
                print(f"{scheduler_output}")
            elif args.model_type == "GPT2":
                scheduler_cmd = f"sbatch --job-name={args.model_instance_id} \
                {cwd}/slurm/GPT2_service.sh {cwd} {args.gateway_host} {args.gateway_port}"
                print(f"Scheduler command: {scheduler_cmd}")
                scheduler_output = subprocess.check_output(scheduler_cmd, shell=True).decode(
                    "utf-8"
                )
                print(f"{scheduler_output}")
            else:
                print(f"Job scheduler does not support model type {args.model_type}")
        except Exception as err:
            print(f"Job scheduler failed: {err}")

    if args.action == "get_status":
        try:
            status_output = subprocess.check_output(
                f"squeue --noheader --name {args.model_instance_id}", shell=True
            ).decode("utf-8")
            print(f"{status_output}")
        except Exception as err:
            print(f"Job status failed: {err}")

    elif args.action == "shutdown":
        try:
            scheduler_cmd = f"scancel --jobname={args.model_instance_id}"
            print(f"Scheduler command: {scheduler_cmd}")
            scheduler_output = subprocess.check_output(
                scheduler_cmd, shell=True
            ).decode("utf-8")
            print(f"{scheduler_output}")
        except Exception as err:
            print(f"Job scheduler failed: {err}")

if __name__ == "__main__":
    main()
