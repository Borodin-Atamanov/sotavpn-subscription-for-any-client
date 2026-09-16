"""The checks of the installer.

They build a root of their own, run the installer inside it and record every
command the installer would have run, so a check never touches the machine it
runs on and never uses the real trash.
"""

import os
import shutil
import sys
import tempfile
import unittest

import install_sotavpn_bridge as installer
import settings


class LocationsCheck(unittest.TestCase):
    """Every path of an installation comes from settings.py, never from the installer."""

    def test_the_system_mode_uses_the_system_directories(self):
        here = installer.locations_of_the_installation(
            installer.SYSTEM_MODE, home_directory="/home/somebody", root=os.sep
        )
        self.assertEqual(here["code_directory"], "/opt/sotavpn-bridge")
        self.assertEqual(here["settings_file"], "/etc/opt/sotavpn-bridge/settings.py")
        self.assertEqual(here["unit_file"], "/etc/systemd/system/sotavpn-bridge.service")
        self.assertEqual(here["command_link"], "/usr/local/bin/sotavpn-bridge")
        self.assertEqual(here["wanted_by"], "multi-user.target")
        self.assertEqual(here["temporary_directory"], "/tmp")

    def test_the_user_mode_uses_the_home_directory(self):
        here = installer.locations_of_the_installation(
            installer.USER_MODE, home_directory="/home/somebody", root=os.sep
        )
        self.assertEqual(here["code_directory"], "/home/somebody/.local/share/sotavpn-bridge")
        self.assertEqual(here["settings_file"], "/home/somebody/.local/share/sotavpn-bridge/settings.py")
        self.assertEqual(here["unit_file"], "/home/somebody/.config/systemd/user/sotavpn-bridge.service")
        self.assertEqual(here["command_link"], "/home/somebody/.local/bin/sotavpn-bridge")
        self.assertEqual(here["wanted_by"], "default.target")
        self.assertEqual(here["temporary_directory"], "%t")

    def test_the_mode_follows_the_account_that_runs_the_installer(self):
        expected = installer.SYSTEM_MODE if os.geteuid() == 0 else installer.USER_MODE
        self.assertEqual(installer.mode_of_the_running_account(), expected)

    def test_the_logs_lie_next_to_the_installed_program_in_both_modes(self):
        for mode in (installer.SYSTEM_MODE, installer.USER_MODE):
            here = installer.locations_of_the_installation(mode, home_directory="/home/somebody", root=os.sep)
            self.assertEqual(here["log_directory"], os.path.join(here["code_directory"], settings.LOGS_DIRECTORY))

    def test_the_two_modes_share_the_one_name_of_an_installation(self):
        for mode in (installer.SYSTEM_MODE, installer.USER_MODE):
            here = installer.locations_of_the_installation(mode, home_directory="/home/somebody", root=os.sep)
            for what in ("code_directory", "settings_file", "unit_file", "command_link"):
                self.assertIn(settings.INSTALL_NAME, here[what], what)

    def test_the_name_of_an_installation_is_written_down_once(self):
        path = os.path.join(installer.PROGRAM_DIRECTORY, installer.SETTINGS_FILE_NAME)
        with open(path, encoding="utf-8") as handle:
            written = handle.read()
        self.assertEqual(written.count(settings.INSTALL_NAME), 1)


class InstallationCheck(unittest.TestCase):
    """An installation into a root of its own, with every command recorded."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="bridge-installation-")
        self.home = os.path.join(self.root, "home")
        os.makedirs(self.home, exist_ok=True)
        self.source = os.path.join(self.root, "clone")
        os.makedirs(os.path.join(self.source, "certs"), exist_ok=True)
        for name in (
            f"{settings.PROGRAM_NAME}.py",
            installer.SETTINGS_FILE_NAME,
            "README.md",
            "LICENSE",
            os.path.basename(installer.__file__),
        ):
            with open(os.path.join(self.source, name), "w", encoding="utf-8") as handle:
                handle.write(f"the file {name} of the checks\n")
        with open(os.path.join(self.source, "certs", "a-certificate.pem"), "w", encoding="utf-8") as handle:
            handle.write("the certificate of the checks\n")
        self.commands = []
        self.messages = []
        self.kept_command_runner = installer.run_a_command
        self.kept_waiting = settings.SECONDS_TO_WAIT_FOR_THE_PROGRAM
        self.kept_say = installer.say
        installer.run_a_command = self.record_the_command
        settings.SECONDS_TO_WAIT_FOR_THE_PROGRAM = 0
        installer.say = self.messages.append
        self.locations = installer.locations_of_the_installation(
            installer.USER_MODE, home_directory=self.home, root=self.root
        )

    def tearDown(self):
        installer.run_a_command = self.kept_command_runner
        settings.SECONDS_TO_WAIT_FOR_THE_PROGRAM = self.kept_waiting
        installer.say = self.kept_say
        shutil.rmtree(self.root, ignore_errors=True)

    def said(self):
        """Everything the installer told the user during this check."""
        return "\n".join(self.messages)

    def record_the_command(self, arguments):
        """Answer every command of the system without running it."""
        self.commands.append(list(arguments))
        if arguments[0] == "gio":
            return 1, "", "the checks do not use the trash"
        if "is-active" in arguments:
            return 0, "active\n", ""
        return 0, "", ""

    def read(self, path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def kept_beside(self, directory):
        """The entries of one directory that a removal left there."""
        return [name for name in os.listdir(directory) if name.endswith("_removed")]

    def test_the_installation_copies_the_program_the_settings_and_the_certificates(self):
        installer.install_the_program(self.source, self.locations)
        for name in (f"{settings.PROGRAM_NAME}.py", installer.SETTINGS_FILE_NAME, "README.md", "LICENSE"):
            self.assertTrue(os.path.exists(os.path.join(self.locations["code_directory"], name)), name)
        self.assertTrue(
            os.path.exists(os.path.join(self.locations["code_directory"], "certs", "a-certificate.pem"))
        )
        self.assertTrue(os.path.exists(self.locations["unit_file"]))
        self.assertEqual(
            os.path.realpath(self.locations["command_link"]),
            os.path.realpath(self.locations["program_file"]),
        )

    def test_the_service_file_points_at_the_installed_paths_and_never_at_the_clone(self):
        installer.install_the_program(self.source, self.locations)
        text = self.read(self.locations["unit_file"])
        self.assertIn(f"ExecStart={sys.executable} {self.locations['program_file']}", text)
        self.assertIn(f"WorkingDirectory={self.locations['code_directory']}", text)
        self.assertIn(f"Environment=TMPDIR={self.locations['temporary_directory']}", text)
        self.assertIn(f"RestartSec={settings.SERVICE_RESTART_PAUSE_SECONDS}", text)
        self.assertIn(f"WantedBy={self.locations['wanted_by']}", text)
        self.assertNotIn(self.source, text)

    def test_the_installation_turns_linger_on_and_makes_the_service_start_at_boot(self):
        installer.install_the_program(self.source, self.locations)
        unit = os.path.basename(self.locations["unit_file"])
        self.assertIn(["systemctl", "--user", "daemon-reload"], self.commands)
        self.assertIn(["systemctl", "--user", "enable", unit], self.commands)
        self.assertIn(["systemctl", "--user", "restart", unit], self.commands)
        self.assertTrue(any("enable-linger" in command for command in self.commands), self.commands)

    def test_a_second_installation_keeps_the_settings_of_the_previous_one_beside_the_new_ones(self):
        installer.install_the_program(self.source, self.locations)
        with open(self.locations["settings_file"], "w", encoding="utf-8") as handle:
            handle.write("the settings of the previous installation\n")
        installer.install_the_program(self.source, self.locations)
        directory = os.path.dirname(self.locations["settings_file"])
        kept = [
            name
            for name in os.listdir(directory)
            if name.endswith(installer.SETTINGS_FILE_NAME) and name != installer.SETTINGS_FILE_NAME
        ]
        self.assertEqual(len(kept), 1, os.listdir(directory))
        self.assertRegex(kept[0], r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}_settings\.py$")
        self.assertIn("the settings of the previous installation", self.read(os.path.join(directory, kept[0])))
        self.assertIn(
            f"the file {installer.SETTINGS_FILE_NAME} of the checks",
            self.read(self.locations["settings_file"]),
        )

    def test_an_installation_from_the_very_directory_of_the_program_copies_nothing(self):
        installer.install_the_program(self.source, self.locations)
        copied = installer.copy_the_program(
            self.locations["code_directory"], self.locations["code_directory"]
        )
        self.assertEqual(copied, [])

    def test_the_removal_takes_the_program_away_and_leaves_the_settings_of_a_system_installation(self):
        system = installer.locations_of_the_installation(
            installer.SYSTEM_MODE, home_directory=self.home, root=self.root
        )
        installer.install_the_program(self.source, system)
        installer.uninstall_the_program(system)
        self.assertFalse(os.path.exists(system["code_directory"]))
        self.assertFalse(os.path.exists(system["unit_file"]))
        self.assertTrue(os.path.exists(system["settings_file"]))
        beside = self.kept_beside(os.path.dirname(system["code_directory"]))
        self.assertEqual(len(beside), 1, os.listdir(os.path.dirname(system["code_directory"])))
        self.assertTrue(
            os.path.exists(os.path.join(os.path.dirname(system["code_directory"]), beside[0], "sotavpn-bridge"))
        )

    def test_the_removal_of_a_user_installation_says_that_the_settings_and_the_logs_went_with_the_program(self):
        installer.install_the_program(self.source, self.locations)
        self.assertEqual(installer.uninstall_the_program(self.locations), 0)
        self.assertIn("went with the program directory", self.said())
        self.assertEqual(
            len(self.kept_beside(os.path.dirname(self.locations["code_directory"]))), 1
        )

    def test_a_removal_never_reads_a_service_file_under_its_own_name_again(self):
        installer.install_the_program(self.source, self.locations)
        installer.uninstall_the_program(self.locations)
        directory = os.path.dirname(self.locations["unit_file"])
        self.assertFalse(os.path.exists(self.locations["unit_file"]))
        for name in os.listdir(directory):
            self.assertFalse(name.endswith(".service"), name)

    def test_the_journal_of_the_previous_run_does_not_count_as_the_new_one(self):
        self.assertFalse(installer.the_journal_belongs_to_a_new_run(17, 17))
        self.assertFalse(installer.the_journal_belongs_to_a_new_run(None, 17))
        self.assertFalse(installer.the_journal_belongs_to_a_new_run(None, None))
        self.assertTrue(installer.the_journal_belongs_to_a_new_run(18, 17))
        # The very first installation has no journal of a previous run at all.
        self.assertTrue(installer.the_journal_belongs_to_a_new_run(17, None))

    def test_the_wait_answers_the_lines_of_the_new_run_only(self):
        kept_identity = installer.identity_of_the_journal
        kept_lines = installer.journal_lines_of_the_installation
        kept_seconds = settings.SECONDS_TO_WAIT_FOR_THE_PROGRAM
        steps = [
            (17, ["2026-09-16 10:57:19 plain HTTP is listening on http://127.0.0.1:25080"]),
            (18, ["2026-09-16 11:00:05 plain HTTP is listening on http://127.0.0.1:25080"]),
        ]
        asked = []

        def identity_of_the_journal(_locations):
            asked.append(1)
            return steps[min(len(asked) - 1, len(steps) - 1)][0]

        def lines_of_the_journal(_locations):
            return steps[min(len(asked) - 1, len(steps) - 1)][1]

        try:
            installer.identity_of_the_journal = identity_of_the_journal
            installer.journal_lines_of_the_installation = lines_of_the_journal
            settings.SECONDS_TO_WAIT_FOR_THE_PROGRAM = 5
            self.assertEqual(
                installer.wait_for_the_program_to_open_its_ports(self.locations, 17),
                ["2026-09-16 11:00:05 plain HTTP is listening on http://127.0.0.1:25080"],
            )
        finally:
            installer.identity_of_the_journal = kept_identity
            installer.journal_lines_of_the_installation = kept_lines
            settings.SECONDS_TO_WAIT_FOR_THE_PROGRAM = kept_seconds

    def test_the_whole_journal_of_the_run_is_read_and_not_a_cut_of_it(self):
        installer.install_the_program(self.source, self.locations)
        os.makedirs(self.locations["log_directory"], exist_ok=True)
        written = [f"the line {number} of the run" for number in range(1, 13)]
        with open(
            os.path.join(self.locations["log_directory"], settings.JOURNAL_FILE_NAME), "w", encoding="utf-8"
        ) as handle:
            handle.write("\n".join(written) + "\n")
        self.assertEqual(installer.journal_lines_of_the_installation(self.locations), written)

    def test_status_tells_the_paths_and_the_state_of_the_service(self):
        installer.install_the_program(self.source, self.locations)
        self.assertEqual(installer.status_of_the_installation(self.locations), 0)
        self.assertIn(self.locations["code_directory"], self.said())
        self.assertIn("active", self.said())

    def test_an_unknown_action_is_refused(self):
        self.assertEqual(installer.main(["install_sotavpn_bridge.py", "whatever"]), 2)
        self.assertIn("unknown action", self.said())

    def test_the_installer_holds_no_install_path_of_its_own(self):
        text = self.read(os.path.join(installer.PROGRAM_DIRECTORY, os.path.basename(installer.__file__)))
        for path in ("/opt/", "/etc/opt", "/var/log", "/usr/local/bin", ".local/share", ".config/systemd"):
            self.assertNotIn(path, text, path)


if __name__ == "__main__":
    unittest.main()
