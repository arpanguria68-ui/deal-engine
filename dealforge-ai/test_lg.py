
import asyncio
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

class S(TypedDict):
    v: int

def run_test():
    builder = StateGraph(S)
    builder.add_node('n', lambda x: x)
    builder.add_edge(START, 'n')
    builder.add_edge('n', END)
    memory = MemorySaver()
    graph = builder.compile(checkpointer=memory)
    
    async def _test():
        try:
            res = await graph.ainvoke({'v': 1}, config={'configurable': {'thread_id': '123'}})
            print('SUCCESS:', res)
        except Exception as e:
            import traceback
            traceback.print_exc()
            
    asyncio.run(_test())

if __name__ == '__main__':
    run_test()

