from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition
import time

def create_keybindings(submit_callback, exit_callback, interrupt_callback):
    kb = KeyBindings()
    
    last_interrupt_time = 0

    @kb.add('c-c')
    def _(event):
        nonlocal last_interrupt_time
        
        # If the editor has text, clear it first
        if event.current_buffer.text:
            event.current_buffer.text = ''
            return
            
        now = time.time()
        # If double pressed within 1 sec when empty, exit
        if now - last_interrupt_time < 1.0:
            exit_callback()
        else:
            last_interrupt_time = now
            if interrupt_callback:
                interrupt_callback()

    @kb.add('escape')
    def _(event):
        """Send an interrupt signal on Escape."""
        if interrupt_callback:
            interrupt_callback()

    @kb.add('enter')
    def _(event):
        """Submit the input when Enter is pressed."""
        # Only submit if the buffer has text
        if event.current_buffer.text.strip():
            submit_callback(event.current_buffer.text)
            event.current_buffer.text = ''

    @kb.add('escape', 'enter')
    def _(event):
        """Alt+Enter as an alternative for Shift-Enter on some terminals."""
        event.current_buffer.insert_text('\n')

    return kb
