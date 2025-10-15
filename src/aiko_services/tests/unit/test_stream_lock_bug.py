# Usage
# ~~~~~
# PYTHONPATH=src pytest src/aiko_services/tests/unit/test_stream_lock_bug.py -v -s
#
# This test reproduces the lock issue found in _create_frames_generator() where 
# stream.lock.acquire() is not properly paired with stream.lock.release() in a 
# try-finally block, causing locks to remain acquired when exceptions occur.

import threading
import time
from typing import Tuple
from unittest.mock import Mock, patch, MagicMock
import traceback

import aiko_services as aiko


def test_create_frames_generator_lock_not_released_on_exception():
    """Test that reproduces the lock not being released when _create_frames_generator encounters exception"""
    
    # Import the actual PipelineElementImpl class
    from aiko_services.main.pipeline import PipelineElementImpl
    from aiko_services.main.utilities.lock import Lock
    
    # Create a real pipeline element for testing
    # We need to patch dependencies to make this work without full pipeline setup
    
    # Create a mock stream with a real lock
    mock_stream = Mock()
    mock_stream.lock = Lock("test_stream_lock")
    mock_stream.state = aiko.StreamState.RUN
    mock_stream.stream_id = "test_stream"
    mock_stream.frame_id = 1
    mock_stream.graph_path = []
    mock_stream.parameters = {}
    mock_stream.queue_response = None
    mock_stream.topic_response = None
    
    # Set up mock methods that will throw exceptions AFTER the lock is acquired
    # This simulates the real bug scenario
    def mock_set_state_that_throws(new_state):
        # This simulates an exception occurring in stream.set_state() which happens
        # AFTER stream.lock.acquire() but BEFORE stream.lock.release()  
        raise RuntimeError("Exception in set_state - this should leave lock unreleased!")
    
    mock_stream.set_state = mock_set_state_that_throws
    
    def working_frame_generator(stream, frame_id):
        """Frame generator that works fine - the exception will happen after it"""
        return aiko.StreamEvent.OKAY, {"frame": frame_id}
    
    # Create a mock pipeline element with minimal setup
    mock_element = Mock(spec=PipelineElementImpl)
    mock_element.name = "TestElement"
    mock_element.logger = Mock()
    mock_element.logger.error = Mock()
    
    # Mock pipeline and thread local dependencies
    mock_pipeline = Mock()
    mock_pipeline._enable_thread_local = Mock()
    mock_pipeline._disable_thread_local = Mock()
    mock_pipeline._process_stream_event = Mock(return_value=aiko.StreamState.RUN)
    mock_pipeline.thread_local = Mock()
    mock_pipeline.thread_local.frame_id = 1
    mock_element.pipeline = mock_pipeline
    
    # Mock get_stream method
    mock_element.get_stream = Mock(return_value=(mock_stream, 1))
    
    # Mock get_parameter method  
    mock_element.get_parameter = Mock(return_value=([], None))
    
    # Mock create_frame method
    mock_element.create_frame = Mock()
    
    # Verify lock is initially not in use
    assert mock_stream.lock.in_use() is None, "Lock should start unused"
    
    # Test the problematic method directly by calling it on our mock element
    # The key is that the exception will happen AFTER lock acquisition
    try:
        # This calls the actual _create_frames_generator method which has the bug
        PipelineElementImpl._create_frames_generator(
            mock_element,
            mock_stream, 
            working_frame_generator,  # This will succeed
            frame_id=1,
            rate=None
        )
    except RuntimeError as e:
        # Expected exception from our mock_set_state_that_throws
        print(f"Expected exception occurred: {e}")
    except Exception as e:
        print(f"Unexpected exception: {e}")
        traceback.print_exc()
    
    # Check if lock is still held (this demonstrates the bug)
    lock_owner = mock_stream.lock.in_use()
    if lock_owner:
        print(f"BUG REPRODUCED: Lock still held by: {lock_owner}")
        print("This demonstrates the exact issue from the logs!")
        print("The lock was acquired but never released due to missing try-finally block")
        
        # Clean up the lock for the test
        mock_stream.lock.release()
        
        # Test passes by successfully demonstrating the bug
        assert True, "Successfully reproduced the lock issue"
    else:
        print("Lock was properly released - the bug may have been fixed")
        assert False, "Expected to reproduce the lock bug but lock was released"


def test_demonstrate_proper_lock_handling():
    """Example of how the lock should be handled properly with try-finally"""
    
    # This demonstrates the CORRECT way to handle locks that should be implemented
    # to fix the bug found in _create_frames_generator
    
    from aiko_services.main.utilities.lock import Lock
    
    # Create a test lock
    test_lock = Lock("test_lock_demo")
    
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
