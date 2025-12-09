class AppTheme:
    def __init__(self, settings: ThemeSettings):
        self.settings = settings

    # existing helpers…
    def primary(self) -> str: return self.settings.primary_color
    def secondary(self) -> str: return self.settings.secondary_color
    def tertiary(self) -> str: return self.settings.tertiary_color

    # semantic helpers
    def confirm(self) -> str:
        return self.settings.accent_confirm

    def cancel(self) -> str:
        return self.settings.accent_cancel

    def warning(self) -> str:
        return self.settings.accent_warning

    def with_alpha_hex(self, hex_color: str, alpha: float) -> str:
        ...
