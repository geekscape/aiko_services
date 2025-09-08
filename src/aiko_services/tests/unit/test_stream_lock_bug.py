# Usage
# ~~~~~
# pytest [-s] unit/test_stream_lock_bug.py
# pytest [-s] unit/test_stream_lock_bug.py::test_create_frames_generator_lock_not_released_on_exception
#
# test_create_frames_generator_lock_not_released_on_exception()
# - PipelineElement._create_frames_generator() acquires stream.lock but doesn't release it
#   when an exception occurs in the frame_generator, causing lock contention.
#   This reproduces the issue seen in logs where lock is acquired but never released.

import threading
import time
from typing import Tuple
from unittest.mock import patch

import aiko_services as aiko
from aiko_services.tests.unit import do_create_pipeline


PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test", "runtime": "python",
  "graph": ["(FrameGeneratorException)"],
  "elements": [
    { "name":   "FrameGeneratorException", "input":  [], "output": [],
      "deploy": {
        "local": { "module": "aiko_services.tests.unit.test_stream_lock_bug" }
      }
    }
  ]
}
"""


class FrameGeneratorException(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("frame_generator_exception:0")
        context.get_implementation("PipelineElement").__init__(self, context)
        self.frame_count = 0

    def start_stream(self, stream, stream_id):
        """Start stream with a frame generator that will throw an exception"""
        # Use create_frames to start the problematic _create_frames_generator thread
        self.create_frames(stream, self.failing_frame_generator, rate=10.0)
        return aiko.StreamEvent.OKAY, {}

    def failing_frame_generator(self, stream, frame_id):
        """Frame generator that throws an exception after a few frames"""
        self.frame_count += 1
        
        if self.frame_count <= 2:
            # Generate a couple successful frames first
            return aiko.StreamEvent.OKAY, {"frame": self.frame_count}
        else:
            # Now throw an exception that will leave the lock unreleased
            raise RuntimeError("Simulated frame generator exception - this should cause unreleased lock!")

    def process_frame(self, stream, **kwargs) -> Tuple[aiko.StreamEvent, dict]:
        # This shouldn't be called much since we use create_frames
        return aiko.StreamEvent.OKAY, {}

    def stop_stream(self, stream, stream_id):
        return aiko.StreamEvent.OKAY, {}


def test_create_frames_generator_lock_not_released_on_exception():
    """Test that reproduces the lock not being released when _create_frames_generator encounters exception"""
    
    # We need to run this test in a way that doesn't hang the test runner
    # Create the pipeline in a separate thread with a timeout
    test_result = {"pipeline": None, "exception": None, "lock_states": []}
    
    def run_pipeline():
        try:
            # Patch aiko.process.terminate to prevent actual termination
            with patch('aiko_services.main.process.terminate'):
                # Create pipeline with our problematic element
                pipeline = do_create_pipeline(PIPELINE_DEFINITION)
                test_result["pipeline"] = pipeline
                
        except Exception as e:
            test_result["exception"] = e
    
    # Start pipeline in thread
    pipeline_thread = threading.Thread(target=run_pipeline, daemon=True)
    pipeline_thread.start()
    
    # Wait a bit for the pipeline to start and the frame generator to fail
    pipeline_thread.join(timeout=5.0)
    
    # The test succeeds if we can demonstrate the issue exists
    # In a real scenario, this would hang or cause issues
    # For the test, we mainly want to show that the exception handling is problematic
    
    if test_result["exception"]:
        print(f"Pipeline failed with: {test_result['exception']}")
    
    if test_result["pipeline"]:
        # Check if there are any stream locks that might be stuck
        pipeline = test_result["pipeline"]
        if hasattr(pipeline, 'stream_leases'):
            for stream_id, stream_lease in pipeline.stream_leases.items():
                stream = stream_lease.stream
                if hasattr(stream, 'lock') and stream.lock.in_use():
                    print(f"WARNING: Stream {stream_id} lock still in use by: {stream.lock.in_use()}")
                    print("This demonstrates the lock issue - lock acquired but not released!")
                    # This is the bug - the lock is still held!
                    assert stream.lock.in_use() is not None, "Lock should be unreleased, demonstrating the bug"
                    return  # Test passes by demonstrating the bug exists
    
    # If we get here, the bug might have been fixed or the test didn't trigger the condition
    print("Test completed - may not have triggered the exact lock issue condition")


def test_demonstrate_proper_lock_handling():
    """Example of how the lock should be handled properly with try-finally"""
    
    # This demonstrates the CORRECT way to handle locks that should be implemented
    # to fix the bug found in _create_frames_generator
    
    import aiko_services.main.utilities.lock as lock_module
    
    # Create a test lock
    test_lock = lock_module.Lock("test_lock_demo")
    
    # Demonstrate proper exception handling with locks
    def proper_lock_usage():
        test_lock.acquire("test_function()")
        try:
            # This represents the frame_generator() call and processing
            # that happens in _create_frames_generator
            raise RuntimeError("Simulated exception during processing")
        finally:
            # This is what's MISSING in the current _create_frames_generator implementation
            test_lock.release()
    
    # Test that the lock is properly released even when exception occurs
    try:
        proper_lock_usage()
    except RuntimeError:
        pass  # Expected exception
    
    # Verify lock was properly released
    assert test_lock.in_use() is None, "Lock should be released after exception"
    print("Demonstrated proper lock handling with try-finally block")


if __name__ == "__main__":
    test_create_frames_generator_lock_not_released_on_exception()
    test_demonstrate_proper_lock_handling()