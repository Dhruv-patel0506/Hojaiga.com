def fibonacci(n: int) -> int:
    """
    Computes the nth Fibonacci number.

    Parameters:
    n (int): The position in the Fibonacci sequence.

    Returns:
    int: The nth Fibonacci number.
    """
    if not isinstance(n, int) or n < 0:
        raise ValueError("Input must be a non-negative integer.")
    
    if n <= 1:
        return n
    
    a, b = 0, 1
    for _ in range(1, n):
        a, b = b, a + b
    return b