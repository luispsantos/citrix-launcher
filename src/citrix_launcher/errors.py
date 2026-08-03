"""Expected application errors shown without a traceback."""


class CitrixLauncherError(Exception):
    """Base class for expected launcher failures."""


class UserCancelledError(CitrixLauncherError):
    """The user cancelled an interactive connection flow."""


class ConfigurationError(CitrixLauncherError):
    """Configuration is missing or invalid."""


class PortalAutomationError(CitrixLauncherError):
    """The browser could not complete a portal step."""


class DownloadError(CitrixLauncherError):
    """An ICA download was missing or invalid."""


class CitrixLaunchError(CitrixLauncherError):
    """Citrix Workspace could not be launched."""
