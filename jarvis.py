import speech_recognition as sr
import datetime
import time
import threading
import os
import string
import queue
import pyttsx3
import keyboard # Import the keyboard library

# --- Setup ---
# Initialize the speech recognizer
r = sr.Recognizer()

# --- Text-to-Speech Setup ---
engine = pyttsx3.init()

voices = engine.getProperty('voices')
# You can try different voices by changing the index
# print("Available voices:")
# for index, voice in enumerate(voices):
#     print(f"{index}: {voice.name}")
# engine.setProperty('voice', voices[0].id) # Example: Set to the first voice
# engine.setProperty('rate', 150) # Example: Set speaking rate (words per minute)
# engine.setProperty('volume', 1.0) # Example: Set volume (0.0 to 1.0)

# --- Gemini Integration Setup ---
import google.generativeai as genai

API_KEY = 'AIzaSyBMurwyrBQIRlf7xU9y7ew63nHtcjKkU9Y' # <-- REPLACE WITH YOUR ACTUAL GEMINI API KEY

if not API_KEY or API_KEY == 'YOUR_ACTUAL_GEMINI_API_KEY':
    print("Error: GEMINI_API_KEY is not set or is still the placeholder.")
    print("Please replace 'YOUR_ACTUAL_GEMINI_API_KEY' in the code with your actual key.")
    model = None
    chat = None
else:
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        print("Gemini model initialized successfully using gemini-1.5-flash.")
        chat = model.start_chat(history=[])
        print("Gemini chat session started.")
    except Exception as e:
        print(f"Error initializing Gemini model or starting chat: {e}")
        model = None
        chat = None

# --- Threading and Communication Setup ---
command_queue = queue.Queue() # Queue to pass commands from listener to main thread
stop_event = threading.Event() # Event to signal all threads to stop
speaking_flag = threading.Event() # Flag to indicate if the assistant is currently speaking
interrupt_speaking_event = threading.Event() # Flag to signal interruption request (set by keyboard)

# --- Text Cleaning Function ---
def clean_text_for_output(text):
    cleaned_text = text.replace('*', '')
    return cleaned_text

# --- Core Functions ---
def speak(audio):
    """Speaks the provided text using the text-to-speech engine in a non-blocking way."""
    print(f"Jarvis says: {audio}")
    print("Speaking flag set.") # Debug print
    speaking_flag.set()
    interrupt_speaking_event.clear() # Clear interrupt flag before starting to speak

    engine.say(audio)

    # Use iterate() in a loop to allow checking for interruption
    engine.startLoop(False)

    # Iterate while engine is busy AND no interruption is requested
    while engine.isBusy() and not interrupt_speaking_event.is_set():
        engine.iterate()
        time.sleep(0.01) # Small delay to prevent high CPU usage

    if interrupt_speaking_event.is_set():
        print("Speech interrupted by keyboard.")
        engine.stop() # Stop the current speech
    else:
         print("Speaking finished naturally.")

    engine.endLoop()
    print("Speaking finished. Speaking flag clear.") # Debug print
    speaking_flag.clear()

# --- Voice Listening Thread (Simpler) ---
class ListeningThread(threading.Thread):
    def __init__(self, queue, stop_e):
        super().__init__()
        self.queue = queue
        self.stop_event = stop_e
        self._is_listening = False

    def run(self):
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=1)
            while not self.stop_event.is_set():
                try:
                    print("Listening...")
                    self._is_listening = True
                    # Use listen() with timeouts
                    audio = r.listen(source, timeout=5, phrase_time_limit=10)

                    if self.stop_event.is_set():
                        break

                    self._is_listening = False
                    print("Recognizing...")

                    # Recognize speech - NO timeout argument here
                    command = r.recognize_google(audio, language='en-in')
                    print(f"User said: {command}\n")

                    # Put the recognized command into the queue
                    self.queue.put(command.lower())
                    print("Command put in queue.") # Debug print

                except sr.UnknownValueError:
                    self._is_listening = False
                    # print("Could not understand audio.") # Optional: silent failure
                    pass

                except sr.RequestError as e:
                    self._is_listening = False
                    print(f"Listening thread error: Could not request results from Google Speech Recognition service; {e}")
                    time.sleep(1)

                except sr.WaitTimeoutError:
                    self._is_listening = False
                    # No speech detected within the timeout, continue listening
                    pass

                except Exception as e:
                    self._is_listening = False
                    print(f"An unexpected error occurred in the listening thread: {e}")
                    time.sleep(1)

        print("Listening thread stopped.")

    def is_listening(self):
        return self._is_listening

# --- Keyboard Listening Thread ---
class KeyboardListenerThread(threading.Thread):
    def __init__(self, interrupt_event, stop_e):
        super().__init__()
        self.interrupt_event = interrupt_event
        self.stop_event = stop_e

    def run(self):
        print("Keyboard listener started.")
        # Hook the 'i' key press event
        keyboard.add_hotkey('i', self.on_i_press)
        # Keep the thread alive until stop_event is set
        while not self.stop_event.is_set():
            time.sleep(0.1) # Small sleep to prevent high CPU usage
        print("Keyboard listener stopped.")

    def on_i_press(self):
        """Callback function when the 'i' key is pressed."""
        if speaking_flag.is_set(): # Only interrupt if Jarvis is speaking
            print(" 'i' key pressed. Signaling interruption.")
            self.interrupt_event.set() # Set the interrupt event

def ask_gemini_with_history(prompt):
    """Sends a prompt to the Gemini chat session and returns the response text."""
    if not chat:
        print("Gemini chat not initialized.")
        return "I'm sorry, my language model is not available at the moment."

    try:
        print(f"Sending to Gemini: {prompt}")
        response = chat.send_message(prompt)
        if response and response.text:
            print(f"Gemini response received.")
            return clean_text_for_output(response.text.strip())
        else:
            print("Gemini response had no text.")
            return "I couldn't generate a text response for that."
    except Exception as e:
        print(f"Error sending message to Gemini chat: {e}")
        return "I encountered an error while processing your request with history."

def process_command(command):
    """Processes the user's command."""
    print(f"Processing command: '{command}'")

    if command is None or command == "":
        print("Received empty or None command. Skipping processing.")
        return True # Continue the loop

    if "exit" in command or "stop" in command:
        speak("Goodbye!")
        return False

    elif "who are you" in command or "your name" in command:
        speak("I am Jarvis, your personal AI assistant.")

    elif "what time is it" in command:
        now = datetime.datetime.now().strftime("%I:%M %p")
        speak(f"The current time is {now}")

    elif "set a reminder" in command:
        speak("Okay, I can help with reminders. Please tell me what you want to be reminded about and when. (Note: This feature needs full implementation)")

    else:
        # --- Send to Gemini for General Queries using chat history ---
        print(f"Sending to Gemini chat: {command}")
        gemini_response = ask_gemini_with_history(command)
        speak(gemini_response)

    return True

# --- Main Loop ---
def main():
    """Main function to run the assistant."""
    print("Initializing Jarvis...")
    if chat:
        speak("Jarvis is ready.")
    else:
        speak("Jarvis is running, but the language model is not available.")

    # Start the voice listening thread
    listening_thread = ListeningThread(command_queue, stop_event)
    listening_thread.daemon = True
    listening_thread.start()
    print("Jarvis is now listening in the background.")

    # Start the keyboard listener thread
    keyboard_thread = KeyboardListenerThread(interrupt_speaking_event, stop_event)
    keyboard_thread.daemon = True
    keyboard_thread.start()
    print("Keyboard listener started for 'i' key.")


    try:
        while not stop_event.is_set():
            # Get command from the queue. This will block until a command is available.
            # Use a small timeout to keep the main loop responsive and check stop_event
            try:
                command = command_queue.get(timeout=0.1)
                print(f"Main loop retrieved from queue: '{command}' (Type: {type(command)})") # Debug print

                # Process the command
                # process_command handles None and ""
                if not process_command(command):
                    break # Exit the main loop if process_command returns False

            except queue.Empty:
                # Queue is empty, continue loop to check stop_event
                pass

            # The speaking interruption is now triggered by the keyboard listener
            # setting the interrupt_speaking_event, which the speak function checks.

    except KeyboardInterrupt:
        print("Ctrl+C detected. Shutting down Jarvis...")
    finally:
        stop_event.set() # Signal all threads to stop
        interrupt_speaking_event.set() # Ensure speaking is interrupted if active

        # Give threads a moment to finish
        listening_thread.join(timeout=1)
        keyboard_thread.join(timeout=1)

        # Stop the pyttsx3 engine cleanly
        engine.stop()
        print("Jarvis shut down.")


# --- Run the Assistant ---
if __name__ == "__main__":
    main()
