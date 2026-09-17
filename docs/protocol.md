# Remote job protocol

The SSH executor uses the user's existing OpenSSH client. On submission it sends a short POSIX shell bootstrap script to the selected host. The bootstrap creates:

    ~/.dreamkeeper/jobs/<id>/
      runner.sh
      command.sh
      pid
      stdout.log
      stderr.log
      exit_code
      start_time
      end_time
      cancelled

runner.sh is launched with nohup and reads the base64-encoded command from command.sh. The initial SSH process only starts the runner and returns its PID. Later status calls reconnect and inspect the durable files.

The command is not sent to a third-party service. It is sent to the selected SSH host, exactly as required to run the experiment there.
