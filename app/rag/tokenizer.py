# Import tiktoken
import tiktoken


# Responsible for tokenizing text
class Tokenizer:

    # Constructor
    def __init__(self):

        # Load the tokenizer for OpenAI models
        # cl100k_base is the token dictionary used to
        # convert text into tokens for OpenAI models.
        self.encoding = tiktoken.get_encoding("cl100k_base")

    # Count the number of tokens in a text
    def count_tokens(self, text: str) -> int:

        # Return the number of encoded tokens
        return len(self.encoding.encode(text))

    # Convert text into tokens
    def encode(self, text: str) -> list[int]:

        # Return encoded tokens
        return self.encoding.encode(text)

    # Convert tokens back into text
    def decode(self, tokens: list[int]) -> str:

        # Return decoded text
        return self.encoding.decode(tokens)
