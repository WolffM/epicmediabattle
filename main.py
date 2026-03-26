"""
Kanto Kompetition - Main CLI Entry Point

A character image competition and management system.
"""

import sys


def show_menu():
    """Display the main menu and get user selection."""
    print("\n" + "=" * 50)
    print("  KANTO KOMPETITION")
    print("=" * 50)
    print("\nSelect a game:\n")
    print("  1. Arena - Character battle tournament")
    print("  0. Exit")
    print()

    while True:
        try:
            choice = input("Enter choice [0-1]: ").strip()
            if choice in ("0", "1"):
                return int(choice)
            print("Invalid choice. Please enter 0 or 1.")
        except (EOFError, KeyboardInterrupt):
            print("\n")
            return 0


def launch_arena():
    """Launch the Arena game."""
    print("\nStarting Arena...")
    print("-" * 50)

    try:
        from games.arena.app import run_server
        run_server()
    except ImportError as e:
        print(f"Error: Could not import Arena module: {e}")
        print("Make sure all dependencies are installed: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"Error starting Arena: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    choice = show_menu()

    if choice == 0:
        print("Goodbye!")
        sys.exit(0)
    elif choice == 1:
        launch_arena()


if __name__ == "__main__":
    main()
