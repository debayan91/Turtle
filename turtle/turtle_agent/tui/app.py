import asyncio
import traceback
from prompt_toolkit import Application
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from turtle_agent.tui.layout import TurtleLayout
from turtle_agent.tui.keybindings import create_keybindings

# Add some nice styles matching the pi-tui aesthetics
style = Style([
    ('status-toolbar', 'bg:#333333 #ffffff'),
    ('line', '#888888'),
])

class TurtleTUI:
    def __init__(self, input_queue: asyncio.Queue, exit_callback, interrupt_callback=None):
        self.input_queue = input_queue
        self.layout_engine = TurtleLayout()
        self.exit_callback = exit_callback
        self.interrupt_callback = interrupt_callback
        
        self.keybindings = create_keybindings(
            submit_callback=self._on_submit,
            exit_callback=self._on_exit,
            interrupt_callback=self._on_interrupt
        )
        
        self.app = Application(
            layout=Layout(self.layout_engine.container, focused_element=self.layout_engine.input_area),
            key_bindings=self.keybindings,
            style=style,
            full_screen=True,
            mouse_support=True
        )
        
    def _on_submit(self, text: str):
        # We push to the async queue. We use put_nowait since it's an unbounded queue.
        try:
            self.input_queue.put_nowait(text)
        except Exception as e:
            self.display_error(f"Error submitting input: {e}")
            
    def _on_exit(self):
        try:
            self.input_queue.put_nowait("/exit")
            self.exit_callback()
        except Exception:
            pass
        self.app.exit()
        
    def _on_interrupt(self):
        if self.interrupt_callback:
            self.interrupt_callback()

    async def run_async(self):
        """Starts the TUI application asynchronously."""
        try:
            await self.app.run_async()
        except Exception as e:
            print(f"Fatal TUI Error: {e}")
            traceback.print_exc()

    def append_transcript(self, text: str, is_markdown: bool = False):
        """Thread-safe and async-safe way to append text to the transcript."""
        # Using call_from_executor or directly since prompt_toolkit 3.0 handles updates during run_async.
        try:
            self.layout_engine.append_transcript(text, is_markdown)
            self.app.invalidate()
        except Exception as e:
            self.display_error(f"Error appending transcript: {e}")
            
    def display_error(self, error_msg: str):
        """The pinnacle of error handling: beautifully surface errors without crashing."""
        formatted_error = f"\n[!] ERROR: {error_msg}\n"
        try:
            self.layout_engine.append_transcript(formatted_error)
            self.app.invalidate()
        except Exception:
            pass # Failsafe
