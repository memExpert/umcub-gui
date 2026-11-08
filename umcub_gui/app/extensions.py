"""What the settings add to the host library: the board name catalog and transport plugins."""
import umcub


def load_extensions(settings):
    """Load the board name files and the plugin folder; returns the errors as text (empty: all loaded)."""
    errors = []
    try:
        umcub.load_board_names(*settings.board_name_files())
    except umcub.UmcubError as e:
        errors.append(str(e))
    folder = settings.plugins_folder()
    for p in umcub.load_plugins(folder):
        if p.error:
            errors.append(f"plugin {p.name} ({p.source}): {p.error}")
    return errors
