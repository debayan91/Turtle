import asyncio
import traceback
from prompt_toolkit import Application
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from turtle_agent.tui.layout import TurtleLayout
from turtle_agent.tui.keybindings import create_keybindings

style = Style([
    ('status-toolbar', 'bg:#16161e #a9b1d6'),
    ('line', '#292e42'),
    ('transcript-frame', '#292e42'),
    ('input-frame', '#292e42'),
    ('prompt', '#7aa2f7 bold'),
    ('title', '#a9b1d6 bold'),
])

class TurtleTUI:
    def __init__(self, input_queue: asyncio.Queue, exit_callback, interrupt_callback=None):
        self.input_queue = input_queue
        self.layout_engine = TurtleLayout()
        self.exit_callback = exit_callback
        self.interrupt_callback = interrupt_callback
        self._picker_future: asyncio.Future | None = None

        self.keybindings = create_keybindings(
            submit_callback=self._on_submit,
            exit_callback=self._on_exit,
            interrupt_callback=self._on_interrupt,
            picker_select_callback=self._on_picker_select,
            picker_cancel_callback=self._on_picker_cancel,
            layout_engine=self.layout_engine
        )

        self.layout = Layout(self.layout_engine.container, focused_element=self.layout_engine.input_area)

        self.app = Application(
            layout=self.layout,
            key_bindings=self.keybindings,
            style=style,
            full_screen=True,
            mouse_support=True
        )

    def _on_submit(self, text: str):
        try:
            self.input_queue.put_nowait(text)
        except Exception as e:
            self.display_error(f"Error submitting input: {e}")

    def _on_exit(self):
        try:
            if not self.app.is_done:
                self.app.exit()
        except Exception:
            pass

    def _on_interrupt(self):
        if self.interrupt_callback:
            self.interrupt_callback()

    def _on_picker_select(self, model: str):
        self.layout_engine.hide_model_picker()
        self.layout.focus(self.layout_engine.input_area)
        if self._picker_future and not self._picker_future.done():
            self._picker_future.set_result(model)
        self.app.invalidate()

    def _on_picker_cancel(self):
        self.layout_engine.hide_model_picker()
        self.layout.focus(self.layout_engine.input_area)
        if self._picker_future and not self._picker_future.done():
            self._picker_future.set_result(None)
        self.app.invalidate()

    async def prompt_model_picker(self, models: list[str], current_model: str = "") -> str | None:
        """Asynchronously show the model picker and await user selection."""
        loop = asyncio.get_running_loop()
        self._picker_future = loop.create_future()
        self.layout_engine.show_model_picker(models, current_model)
        self.layout.focus(self.layout_engine.picker_control)
        self.app.invalidate()
        return await self._picker_future

    async def run_async(self):
        try:
            await self.app.run_async()
        except Exception as e:
            print(f"Fatal TUI Error: {e}")
            traceback.print_exc()

    def append_transcript(self, text: str, is_markdown: bool = False):
        try:
            self.layout_engine.append_transcript(text, is_markdown)
            self.app.invalidate()
        except Exception as e:
            self.display_error(f"Error appending transcript: {e}")

    def display_error(self, error_msg: str):
        formatted_error = f"\n[#f7768e]✗ ERROR:[/] [#a9b1d6]{error_msg}[/]\n"
        try:
            self.layout_engine.append_transcript(formatted_error)
            self.app.invalidate()
        except Exception:
            pass
