from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition

def create_keybindings(submit_callback, exit_callback):
    kb = KeyBindings()

    @kb.add('c-c')
    def _(event):
        """Exit the application when Ctrl-C is pressed."""
        exit_callback()

    @kb.add('enter')
    def _(event):
        """Submit the input when Enter is pressed."""
        # Only submit if the buffer has text
        if event.current_buffer.text.strip():
            submit_callback(event.current_buffer.text)
            event.current_buffer.text = ''

    @kb.add('s-enter')
    def _(event):
        """Insert a newline when Shift-Enter is pressed."""
        event.current_buffer.insert_text('\n')
        
    @kb.add('escape', 'enter')
    def _(event):
        """Alt+Enter as an alternative for Shift-Enter on some terminals."""
        event.current_buffer.insert_text('\n')

    return kb
