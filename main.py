#!/usr/bin/env python3
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))

from src.repl import REPL

def main():
    parser = argparse.ArgumentParser(description='Small-C Interactive Interpreter')
    parser.add_argument('--author', default='Student', help='Author name shown in ABOUT')
    args = parser.parse_args()

    repl = REPL(author=args.author)
    repl.run()

if __name__ == '__main__':
    main()