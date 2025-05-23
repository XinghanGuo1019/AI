# get_worker_client.py
import asyncio
import json
import sys
import os
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()  # load environment variables from .env

class MCPClient:
    """
    A class to handle the MCP client for Workday API interactions.
    """
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack() # for async context management
        self.llm = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("BASE_URL"))
        self.model = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
    
    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server

        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None # Use current environment variables
        )
        
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])

    async def process_query(self, query: str) -> str:
        """Process a query using LLM and available tools
        Args:
            query: The query to process
        Returns:
            The response from the LLM or tool
        """
        messages = [
            {
                "role": "system",
                "content": "You are a professional AI Assistant. You can use the tools in the MCP Server to complete Workday HCM related tasks requested by the user."
            },
            {
                "role": "user",
                "content": query
            }
        ]
        # List available tools
        response = await self.session.list_tools()
        available_tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            },
        } for tool in response.tools]

        # Initial LLM API call
        try:
            response = self.llm.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                messages=messages,
                tools=available_tools
            )
        except Exception as e:
            print(f"Error in LLM call: {e}")
        print(f"LLM response: {response.choices[0]}")
        # Process response and handle tool calls
        final_text= []
        messages.append(response.choices[0].message)
        if hasattr(response.choices[0].message, 'tool_calls') and response.choices[0].message.tool_calls:
            for tool_call in response.choices[0].message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                    print(f"Tool name: {tool_name}, Raw args: {tool_args}")
                except Exception as e:
                    print(f"Error parsing tool args: {e}")

                print(f"Calling tool {tool_name} with args {tool_args}")
                final_text.append(f"Calling tool {tool_name} with args {tool_args}")
                tool_response = await self.session.call_tool(tool_name, tool_args)

                tool_result_content = tool_response.content
                if isinstance(tool_response, list):
                    text_content = ""
                    for item in tool_response:
                        if hasattr(item, "text"):
                            text_content += item.text
                    tool_result_content = text_content
                elif not isinstance(tool_response, str):
                    tool_result_content = str(tool_response)
                final_text.append(tool_result_content)
                print(f"Tool result content: {tool_result_content}")

                tool_message = {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result_content
                }
                messages.append(tool_message)

                # Check if the assistant's message contains prompts for further tool calls
                try:
                    # Check if the tool response contains prompt template information
                    if isinstance(tool_args, dict) and "prompt_template" in tool_args and "template_args" in tool_args:
                        prompt_template = tool_args["prompt_template"]
                        template_args = tool_args["template_args"]
                        string_args = {k: str(v) for k, v in template_args.items()}
                        
                        template_response = await self.session.get_prompt(prompt_template, string_args)
                        
                        if hasattr(template_response, 'messages') and hasattr(template_response, 'message'):
                            for message in template_response.messages:
                                if message.role == "assistant":
                                    content = message.content.text if hasattr(message.content, 'text') else message.content
                                    template_message = {
                                        "role": message.role,
                                        "content": content
                                    }
                                    final_text.append(f"LLM response: {template_message}")
                except Exception as e:
                    print(f"Error processing template information: {e}")

                # Another call to LLM with updated messages
                try:
                    final_response = self.llm.chat.completions.create(
                        model=self.model,
                        max_tokens=4096,
                        temperature=0.5,
                        messages=messages,
                    )
                    final_text.append("LLM final response: " + final_response.choices[0].message.content)
                except Exception as e:
                    print(f"Error in final LLM call: {e}")
                    final_text.append("Error in final LLM call: " + str(e))
                    return "\n".join(final_text)
                
        else:
            final_text.append(response.choices[0].message.content)

        return "\n".join(final_text)


    async def chat_loop(self):
        """Run an interactive chat loop
        
        This function allows the user to input queries and receive responses
        from the MCP server. The loop continues until the user types 'quit'.
        """
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break

                response = await self.process_query(query)
                print("\n" + response)

            except Exception as e:
                print(f"\nError: {str(e)}") 

    async def cleanup(self):
        """Clean up resources
        This function closes the exit stack and any open connections.
        Handles ProcessLookupError that may occur if process already terminated.
        """
        try:
            await self.exit_stack.aclose()
        except ProcessLookupError:
            # Process already terminated, nothing to do
            pass
        except Exception as e:
            print(f"Error during cleanup: {e}")

async def main():
    """Main function to run the MCP client
    This function initializes the MCP client, connects to the server,
    and starts the chat loop.
    """
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)

    client = MCPClient()
    try:
        print("Connecting to server...")
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())

    #     you need to activate the virtual environment
    #     .venv/Script/activate
    #     python get_worker_client.py mcp-workday/get_worker_server.py
