#!/usr/bin/env python3
"""Launcher script for Travel Planner Agent."""

import sys
import os

# Charger les variables d'environnement depuis .env si présent
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def main():
    """Main launcher."""
    print("🌍 Travel Planner Agent - Launcher")
    print("=" * 50)
    print("\nChoose how to run the agent:\n")
    print("1. 🖥️  GUI Interface (Graphical - Recommended)")
    print("2. 💻 CLI Interface (Command Line)")
    print("3. ❌ Exit\n")

    choice = input("Enter your choice (1-3): ").strip()

    if choice == "1":
        print("\nLaunching GUI Interface...")
        print("(This may take a moment to start)\n")
        try:
            from travel_planner_gui import main as gui_main
            gui_main()
        except ImportError as e:
            print(f"❌ Error: Could not import GUI. Make sure tkinter is installed.")
            print(f"   Error: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error launching GUI: {e}")
            sys.exit(1)

    elif choice == "2":
        print("\nLaunching CLI Interface...\n")
        try:
            from travel_planner import travel_planner_agent
            travel_planner_agent()
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)

    elif choice == "3":
        print("\nGoodbye! ✈️")
        sys.exit(0)

    else:
        print("\n❌ Invalid choice. Please enter 1, 2, or 3.")
        sys.exit(1)


if __name__ == "__main__":
    main()