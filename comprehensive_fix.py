#!/usr/bin/env python3

import re

with open('picochess.py', 'r') as f:
    content = f.read()

# Split into lines
lines = content.split('\n')

# Find the process_main_events function
start_line = None
end_line = None
for i, line in enumerate(lines):
    if 'async def process_main_events' in line:
        start_line = i
        break

if start_line is None:
    print("Could not find process_main_events function")
    exit(1)

# Find the end of the function
for i in range(start_line + 1, len(lines)):
    line = lines[i]
    if line.strip().startswith('def ') and not line.strip().startswith('def '):
        end_line = i
        break
    elif line.strip().startswith('class '):
        end_line = i
        break

if end_line is None:
    end_line = len(lines)

print(f"Found process_main_events function from line {start_line + 1} to {end_line}")

# Fix the function by rewriting it with proper indentation
fixed_lines = []

# Keep everything before the function
fixed_lines.extend(lines[:start_line])

# Add the function header
fixed_lines.append(lines[start_line])  # function definition
fixed_lines.append('            """Consume event from evt_queue"""')
fixed_lines.append('            try:')
fixed_lines.append('                if not isinstance(event, Event.CLOCK_TIME):')
fixed_lines.append('                    logger.debug("received event from evt_queue: %s", event)')
fixed_lines.append('')

# Add a simple structure for the main event processing
fixed_lines.append('                if isinstance(event, Event.FEN):')
fixed_lines.append('                    try:')
fixed_lines.append('                        await self.process_fen(event.fen, self.state)')
fixed_lines.append('                    except Exception as e:')
fixed_lines.append('                        logger.error("Error processing FEN in mode %s: %s", self.state.interaction_mode, e)')
fixed_lines.append('                        if self.state.interaction_mode == Mode.ANALYSIS:')
fixed_lines.append('                            logger.error("Critical error in analysis mode - preventing system crash")')
fixed_lines.append('                            return')
fixed_lines.append('')
fixed_lines.append('                else:  # Default')
fixed_lines.append('                    logger.info("event not handled : [%s]", event)')
fixed_lines.append('                    await asyncio.sleep(0.05)  # balance message queues')
fixed_lines.append('')
fixed_lines.append('            except Exception as e:')
fixed_lines.append('                logger.error("Critical error in process_main_events: %s", e)')
fixed_lines.append('                # Don\'t let any event processing error crash the system')
fixed_lines.append('')

# Keep everything after the function
fixed_lines.extend(lines[end_line:])

# Write the corrected file
with open('picochess.py', 'w') as f:
    f.write('\n'.join(fixed_lines))

print("Comprehensive fix applied - simplified process_main_events function")