import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from requests.exceptions import ConnectionError, ReadTimeout

import aider
from aider.coders import Coder
from aider.commands import Commands
from aider.help import Help, fname_to_url, get_help_extra_package
from aider.io import InputOutput
from aider.models import Model


class TestHelp(unittest.TestCase):
    @staticmethod
    def retry_with_backoff(func, max_time=60, initial_delay=1, backoff_factor=2):
        """
        Execute a function with exponential backoff retry logic.

        Args:
            func: Function to execute
            max_time: Maximum time in seconds to keep retrying
            initial_delay: Initial delay between retries in seconds
            backoff_factor: Multiplier for delay after each retry

        Returns:
            The result of the function if successful

        Raises:
            The last exception encountered if all retries fail
        """
        start_time = time.time()
        delay = initial_delay
        last_exception = None

        while time.time() - start_time < max_time:
            try:
                return func()
            except (ReadTimeout, ConnectionError) as e:
                last_exception = e
                time.sleep(delay)
                delay = min(delay * backoff_factor, 15)  # Cap max delay at 15 seconds

        # If we've exhausted our retry time, raise the last exception
        if last_exception:
            raise last_exception
        raise Exception("Retry timeout exceeded but no exception was caught")

    @classmethod
    def setUpClass(cls):
        io = InputOutput(pretty=False, yes=True)

        GPT35 = Model("gpt-3.5-turbo")

        coder = Coder.create(GPT35, None, io)
        commands = Commands(io, coder)

        help_coder_run = MagicMock(return_value="")
        aider.coders.HelpCoder.run = help_coder_run

        def run_help_command():
            try:
                commands.cmd_help("hi")
            except aider.commands.SwitchCoder:
                pass
            else:
                # If no exception was raised, fail the test
                assert False, "SwitchCoder exception was not raised"

        # Use retry with backoff for the help command that loads models
        cls.retry_with_backoff(run_help_command)

        help_coder_run.assert_called_once()

    def test_init(self):
        help_inst = Help()
        self.assertIsNotNone(help_inst.retriever)

    def test_ask_without_mock(self):
        help_instance = Help()
        question = "What is aider?"
        result = help_instance.ask(question)

        self.assertIn(f"# Question: {question}", result)
        self.assertIn("<doc", result)
        self.assertIn("</doc>", result)
        self.assertGreater(len(result), 100)  # Ensure we got a substantial response

        # Check for some expected content (adjust based on your actual help content)
        self.assertIn("aider", result.lower())
        self.assertIn("ai", result.lower())
        self.assertIn("chat", result.lower())

        # Assert that there are more than 5 <doc> entries
        self.assertGreater(result.count("<doc"), 5)

    def test_fname_to_url_unix(self):
        # Test relative Unix-style paths
        self.assertEqual(
            fname_to_url("website/docs/index.md"), "https://aider.chat/docs"
        )
        self.assertEqual(
            fname_to_url("website/docs/usage.md"), "https://aider.chat/docs/usage.html"
        )
        self.assertEqual(fname_to_url("website/_includes/header.md"), "")

        # Test absolute Unix-style paths
        self.assertEqual(
            fname_to_url("/home/user/project/website/docs/index.md"),
            "https://aider.chat/docs",
        )
        self.assertEqual(
            fname_to_url("/home/user/project/website/docs/usage.md"),
            "https://aider.chat/docs/usage.html",
        )
        self.assertEqual(
            fname_to_url("/home/user/project/website/_includes/header.md"), ""
        )

    def test_fname_to_url_windows(self):
        # Test relative Windows-style paths
        self.assertEqual(
            fname_to_url(r"website\docs\index.md"), "https://aider.chat/docs"
        )
        self.assertEqual(
            fname_to_url(r"website\docs\usage.md"), "https://aider.chat/docs/usage.html"
        )
        self.assertEqual(fname_to_url(r"website\_includes\header.md"), "")

        # Test absolute Windows-style paths
        self.assertEqual(
            fname_to_url(r"C:\Users\user\project\website\docs\index.md"),
            "https://aider.chat/docs",
        )
        self.assertEqual(
            fname_to_url(r"C:\Users\user\project\website\docs\usage.md"),
            "https://aider.chat/docs/usage.html",
        )
        self.assertEqual(
            fname_to_url(r"C:\Users\user\project\website\_includes\header.md"), ""
        )

    def test_fname_to_url_edge_cases(self):
        # Test paths that don't contain 'website'
        self.assertEqual(fname_to_url("/home/user/project/docs/index.md"), "")
        self.assertEqual(fname_to_url(r"C:\Users\user\project\docs\index.md"), "")

        # Test empty path
        self.assertEqual(fname_to_url(""), "")

        # Test path with 'website' in the wrong place
        self.assertEqual(fname_to_url("/home/user/website_project/docs/index.md"), "")

    def test_get_help_extra_package_local_checkout(self):
        """Test that get_help_extra_package returns local package when pyproject.toml exists."""
        with patch("pathlib.Path.cwd") as mock_cwd:
            # Create a mock path that returns a temporary directory
            mock_path = MagicMock(spec=Path)
            mock_path.__truediv__ = MagicMock(return_value=Path("pyproject.toml"))
            mock_path.parent = mock_path
            mock_cwd.return_value = mock_path

            # Create a temporary directory with pyproject.toml
            with patch("pathlib.Path") as mock_path_class:
                mock_path_instance = MagicMock()
                mock_path_instance.exists.return_value = True
                mock_path_class.return_value = mock_path_instance
                mock_path_class.cwd.return_value = mock_path

                # When we call get_help_extra_package, it should find pyproject.toml
                # and return the local package
                result = get_help_extra_package()
                # The function should return 'aider-chat[help]' for local checkout
                self.assertEqual(result, "aider-chat[help]")

    def test_get_help_extra_package_pinned_release(self):
        """Test that get_help_extra_package returns pinned version when no pyproject.toml."""
        with patch("pathlib.Path.cwd") as mock_cwd:
            # Create a mock path that doesn't find pyproject.toml
            mock_path = MagicMock(spec=Path)
            mock_path.__truediv__ = MagicMock(return_value=Path("pyproject.toml"))
            mock_path.parent = mock_path
            mock_cwd.return_value = mock_path

            # Create a temporary directory without pyproject.toml
            with patch("pathlib.Path") as mock_path_class:
                mock_path_instance = MagicMock()
                mock_path_instance.exists.return_value = False
                mock_path_class.return_value = mock_path_instance
                mock_path_class.cwd.return_value = mock_path

                # When we call get_help_extra_package, it should NOT find pyproject.toml
                # and return the pinned version
                result = get_help_extra_package()
                # The function should return 'aider-chat[help]=={__version__}' for pinned release
                self.assertIn("aider-chat[help]==", result)


if __name__ == "__main__":
    unittest.main()
