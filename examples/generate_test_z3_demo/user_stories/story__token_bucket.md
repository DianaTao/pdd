# Story: Token bucket rate limiter

<!-- pdd-story-prompts: token_bucket_python.prompt -->

## Context

A rate limiter service uses a token bucket to throttle consume requests.
Each caller starts with a full bucket and drains it as requests are made.
A background job periodically calls refill to restore tokens.

## Covers

- R1: creating a bucket with non-positive or non-integer capacity raises ValueError
- R2: bucket created without explicit initial count starts full (tokens_available equals capacity)
- R3: successful consume reduces tokens_available by exactly the requested amount and returns True
- R4: consume request for more tokens than available returns False and leaves bucket unchanged
- R5: refill within capacity increases tokens_available by the refill amount
- R6: refill that would exceed capacity is capped so tokens_available equals capacity
- R7: capacity property always returns the immutable positive integer set at construction

## Acceptance Criteria

- [ ] R1: Creating a bucket with a non-positive or non-integer capacity raises ValueError
- [ ] R2: A bucket created without an explicit initial count starts full (tokens_available equals capacity)
- [ ] R3: A successful consume reduces tokens_available by exactly the requested amount and returns True
- [ ] R4: A consume request for more tokens than available is rejected (returns False) and the bucket is unchanged
- [ ] R5: A refill call within capacity increases tokens_available by the refill amount
- [ ] R6: A refill call that would exceed capacity is capped so tokens_available equals capacity
- [ ] R7: The capacity property always returns the immutable positive integer set at construction

## Scenarios

### R1 — invalid capacity rejected at construction
Given capacity=0
When TokenBucket(capacity=0) is called
Then ValueError is raised

Given capacity=-1
When TokenBucket(capacity=-1) is called
Then ValueError is raised

### R2 — bucket starts full by default
Given capacity=10 and no initial tokens_available
When TokenBucket(10) is constructed
Then tokens_available equals 10

### R3 — exact state transition on success
Given a bucket with capacity=10 and tokens_available=8
When consume(3) is called
Then the result is True
And tokens_available equals exactly 5

### R4 — rejection when insufficient tokens
Given a bucket with capacity=10 and tokens_available=2
When consume(5) is called
Then the result is False
And tokens_available remains 2

### R5 — refill within capacity
Given a bucket with capacity=10 and tokens_available=2
When refill(5) is called
Then tokens_available equals 7

### R6 — refill never exceeds capacity
Given a bucket with capacity=10 and tokens_available=9
When refill(50) is called
Then tokens_available equals 10

Given a bucket with capacity=5 and tokens_available=0
When refill(100) is called
Then tokens_available equals 5
And tokens_available <= capacity

### R7 — capacity property is read-only
Given a bucket with capacity=10
When the capacity property is read
Then it returns 10
